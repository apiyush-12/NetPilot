import json
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "lab" / "compose.yaml"
LOG_DIR = ROOT / "agent" / "logs"
LOG_FILE = LOG_DIR / "events.jsonl"
STATE_FILE = LOG_DIR / "controller_state.json"

CLIENT_IP = "10.66.1.10"
SERVER_IP = "10.66.2.10"
CLIENT_DEST_NET = "10.66.2.0/24"
SERVER_DEST_NET = "10.66.1.0/24"
ROUTERS = {
    "router-a": ("10.66.1.2", "10.66.2.2"),
    "router-b": ("10.66.1.3", "10.66.2.3"),
}

CHECK_INTERVAL_SECONDS = 5
FAILURE_THRESHOLD = 3
RECOVERY_RETRY_SECONDS = 30
FAILBACK_STABLE_CHECKS = 6
COMMAND_TIMEOUT_SECONDS = 15

LOG_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def log(event_type, **details):
    record = {
        "timestamp": now_iso(),
        "event_id": str(uuid.uuid4()),
        "event": event_type,
        **details,
    }
    line = json.dumps(record)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def compose(*args):
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        text=True,
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


def exec_in(service, *args):
    return compose("exec", "-T", service, *args)


def service_running(service):
    result = compose("ps", "--status", "running", "-q", service)
    if result.returncode != 0:
        raise RuntimeError(f"Cannot inspect {service}: {result.stderr.strip()}")
    return bool(result.stdout.strip())


def ping(service, address):
    return exec_in(service, "ping", "-c", "1", "-W", "2", address).returncode == 0


def route_gateway(service, destination):
    result = exec_in(service, "ip", "-4", "route", "get", destination)
    if result.returncode != 0:
        raise RuntimeError(f"Route inspection failed for {service}: {result.stderr.strip()}")
    match = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)\b", result.stdout)
    return match.group(1) if match else None


def active_router():
    client_gw = route_gateway("client", SERVER_IP)
    server_gw = route_gateway("server", CLIENT_IP)
    for name, (client_side, server_side) in ROUTERS.items():
        if (client_gw, server_gw) == (client_side, server_side):
            return name
    return "inconsistent"


def router_usable(name):
    if not service_running(name):
        return False
    client_side, server_side = ROUTERS[name]
    return (
        ping("client", client_side)
        and ping(name, SERVER_IP)
        and ping("server", server_side)
    )


def set_routes(name):
    client_gw, server_gw = ROUTERS[name]
    client = exec_in(
        "client", "ip", "route", "replace", CLIENT_DEST_NET, "via", client_gw
    )
    if client.returncode != 0:
        log("ROUTE_UPDATE_ERROR", service="client", target=name,
            detail=client.stderr.strip())
        return False
    server = exec_in(
        "server", "ip", "route", "replace", SERVER_DEST_NET, "via", server_gw
    )
    if server.returncode != 0:
        log("ROUTE_UPDATE_ERROR", service="server", target=name,
            detail=server.stderr.strip())
        return False
    return True


def verify_routes_and_connectivity(name):
    return active_router() == name and ping("client", SERVER_IP)


def switch_router(target, reason, incident_id=None):
    previous = active_router()
    if previous == target:
        return verify_routes_and_connectivity(target)

    if not router_usable(target):
        log("TARGET_ROUTER_UNAVAILABLE", target=target, incident_id=incident_id)
        return False

    started = time.monotonic()
    log("ROUTE_CHANGE_STARTED", previous=previous, target=target,
        reason=reason, incident_id=incident_id)

    updated = set_routes(target)
    if updated:
        time.sleep(1)
    if updated and verify_routes_and_connectivity(target):
        log("ROUTE_CHANGE_SUCCESS", previous=previous, target=target,
            reason=reason, incident_id=incident_id,
            duration_ms=round((time.monotonic() - started) * 1000))
        return True

    log("ROUTE_CHANGE_FAILED", previous=previous, target=target,
        reason=reason, incident_id=incident_id)
    # Do NOT roll back to a router that is known to be unavailable.
    if previous in ROUTERS and router_usable(previous):
        rollback_updated = set_routes(previous)
        rollback_ok = rollback_updated and verify_routes_and_connectivity(previous)
        log("ROLLBACK_RESULT", target=previous, verified=rollback_ok,
            incident_id=incident_id)
    else:
        log("ROLLBACK_SKIPPED", previous=previous,
            reason="Previous route unavailable or inconsistent",
            incident_id=incident_id)
    return False


def default_state():
    return {"incident_id": None, "next_retry_at": 0.0, "status": "HEALTHY", "attempts": 0}


def load_state():
    if not STATE_FILE.exists():
        return default_state()
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("State file is not a JSON object")
        return {
            "incident_id": state.get("incident_id"),
            "next_retry_at": float(state.get("next_retry_at", 0)),
            "status": state.get("status", "HEALTHY"),
            "attempts": int(state.get("attempts", 0)),
        }
    except (ValueError, TypeError, OSError) as error:
        log("STATE_LOAD_ERROR", detail=str(error))
        return default_state()


def save_state(state):
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(STATE_FILE)


def choose_recovery_target(current):
    # If the current path is broken, try the alternative.
    # If routing is inconsistent, first try to reconcile to Router B.
    return "router-a" if current == "router-b" else "router-b"


def main():
    state = load_state()
    failed_checks = 0
    primary_stable_checks = 0
    next_failback_at = 0.0

    if not COMPOSE_FILE.is_file():
        raise SystemExit(f"Missing Docker Compose file: {COMPOSE_FILE}")

    log("NETPILOT_V3_STARTED", pending_incident=state["incident_id"])

    try:
        while True:
            try:
                # An unavailable Docker container must not be misclassified
                # as a recoverable network path failure.
                if not service_running("client") or not service_running("server"):
                    failed_checks = 0
                    primary_stable_checks = 0
                    log("LAB_COMPONENT_UNAVAILABLE")
                    time.sleep(CHECK_INTERVAL_SECONDS)
                    continue

                current = active_router()
                healthy = ping("client", SERVER_IP)

                if healthy:
                    failed_checks = 0

                    if state["incident_id"] is not None:
                        log("INCIDENT_RESOLVED", incident_id=state["incident_id"],
                            active_router=current, resolution="CONNECTIVITY_RESTORED")
                        state = default_state()
                        save_state(state)

                    log("NETWORK_HEALTHY", active_router=current)

                    if current == "router-b":
                        if router_usable("router-a"):
                            primary_stable_checks += 1
                        else:
                            primary_stable_checks = 0
                        if (primary_stable_checks >= FAILBACK_STABLE_CHECKS
                                and time.monotonic() >= next_failback_at):
                            log("PRIMARY_STABLE", checks=primary_stable_checks)
                            succeeded = switch_router("router-a", "AUTOMATIC_FAILBACK")
                            log("FAILBACK_RESULT", successful=succeeded)
                            primary_stable_checks = 0
                            next_failback_at = time.monotonic() + RECOVERY_RETRY_SECONDS
                    else:
                        primary_stable_checks = 0
                        if current == "inconsistent":
                            log("ROUTE_STATE_INCONSISTENT",
                                action="No automatic change while connectivity is healthy")

                else:
                    failed_checks += 1
                    primary_stable_checks = 0
                    log("CONNECTIVITY_FAILURE", consecutive_failures=failed_checks,
                        active_router=current)

                    if failed_checks >= FAILURE_THRESHOLD:
                        if state["incident_id"] is None:
                            state["incident_id"] = str(uuid.uuid4())
                            state["next_retry_at"] = 0.0
                            state["status"] = "DEGRADED"
                            state["attempts"] = 0
                            save_state(state)
                            log("INCIDENT_CREATED", incident_id=state["incident_id"],
                                active_router=current)

                        if time.time() >= state["next_retry_at"]:
                            target = choose_recovery_target(current)
                            state["attempts"] += 1
                            state["status"] = "RECOVERING"
                            save_state(state)
                            log("RECOVERY_ATTEMPT", incident_id=state["incident_id"],
                                attempt=state["attempts"], current=current, target=target)
                            recovered = switch_router(
                                target, "CONNECTIVITY_FAILURE", state["incident_id"]
                            )
                            if recovered:
                                log("INCIDENT_RESOLVED", incident_id=state["incident_id"],
                                    active_router=target, resolution="AUTOMATED_RECOVERY")
                                state = default_state()
                                save_state(state)
                                failed_checks = 0
                            else:
                                state["next_retry_at"] = (
                                    time.time() + RECOVERY_RETRY_SECONDS
                                )
                                state["status"] = "DEGRADED"
                                save_state(state)
                                log("INCIDENT_DEGRADED", incident_id=state["incident_id"],
                                    recovery_attempts=state["attempts"])
                                log("RECOVERY_RETRY_SCHEDULED",
                                    incident_id=state["incident_id"],
                                    delay_seconds=RECOVERY_RETRY_SECONDS)

            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                log("MONITOR_ERROR", detail=str(error))

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        log("NETPILOT_V3_STOPPED", pending_incident=state["incident_id"])


if __name__ == "__main__":
    main()
