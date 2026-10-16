import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------- CONFIGURATION ----------

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "lab"
LOG_DIR = ROOT / "agent" / "logs"
LOG_FILE = LOG_DIR / "events.jsonl"

DESTINATION = "10.66.2.10"
CLIENT_NETWORK = "10.66.2.0/24"
SERVER_NETWORK = "10.66.1.0/24"

ROUTERS = {
    "router-a": {
        "client_gateway": "10.66.1.2",
        "server_gateway": "10.66.2.2",
    },
    "router-b": {
        "client_gateway": "10.66.1.3",
        "server_gateway": "10.66.2.3",
    },
}

CHECK_INTERVAL = 5
FAILURE_THRESHOLD = 3
FAILBACK_THRESHOLD = 6
COMMAND_TIMEOUT = 15

LOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------- COMMAND EXECUTION ----------

def docker(*args):
    command = [
        "docker", "compose",
        "-f", str(LAB / "compose.yaml"),
        *args,
    ]

    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT,
    )


def execute(service, *args):
    return docker("exec", "-T", service, *args)


def log_event(event_type, **details):
    event = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "event_id": str(uuid.uuid4()),
        "event": event_type,
        **details,
    }

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event) + "\n")

    print(json.dumps(event), flush=True)


# ---------- NETWORK INSPECTION ----------

def ping(service, destination):
    result = execute(
        service, "ping", "-c", "1",
        "-W", "2", destination
    )
    return result.returncode == 0


def connectivity_healthy():
    return ping("client", DESTINATION)


def get_route(service, destination):
    result = execute(
        service, "ip", "-4", "route",
        "get", destination
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    return result.stdout.strip()


def active_router():
    client_route = get_route("client", DESTINATION)
    server_route = get_route("server", "10.66.1.10")

    for name, config in ROUTERS.items():
        forward = "via " + config["client_gateway"]
        reverse = "via " + config["server_gateway"]

        if forward in client_route and reverse in server_route:
            return name

    return "inconsistent"


def router_running(name):
    result = docker(
        "ps", "--status", "running",
        "-q", name
    )
    return (
        result.returncode == 0
        and bool(result.stdout.strip())
    )


def router_usable(name):
    if not router_running(name):
        return False

    config = ROUTERS[name]

    return (
        ping("client", config["client_gateway"])
        and ping(name, "10.66.2.10")
        and ping("server", config["server_gateway"])
    )


# ---------- RECOVERY CONTROLLER ----------

def set_routes(name):
    config = ROUTERS[name]

    client = execute(
        "client", "ip", "route", "replace",
        CLIENT_NETWORK, "via",
        config["client_gateway"],
    )

    server = execute(
        "server", "ip", "route", "replace",
        SERVER_NETWORK, "via",
        config["server_gateway"],
    )

    if client.returncode != 0 or server.returncode != 0:
        log_event(
            "ROUTE_UPDATE_ERROR",
            target=name,
            client_error=client.stderr.strip(),
            server_error=server.stderr.strip(),
        )
        return False

    return True


def verify_route(name):
    return (
        active_router() == name
        and connectivity_healthy()
    )


def change_router(target, reason, incident_id=None):
    start = time.monotonic()
    previous = active_router()

    if previous == target:
        return verify_route(target)

    if not router_usable(target):
        log_event(
            "TARGET_ROUTER_UNAVAILABLE",
            target=target,
            incident_id=incident_id,
        )
        return False

    log_event(
        "ROUTE_CHANGE_STARTED",
        previous=previous,
        target=target,
        reason=reason,
        incident_id=incident_id,
    )

    try:
        updated = set_routes(target)

        if updated:
            time.sleep(1)

        if updated and verify_route(target):
            duration = round(
                (time.monotonic() - start) * 1000
            )

            log_event(
                "ROUTE_CHANGE_SUCCESS",
                previous=previous,
                target=target,
                incident_id=incident_id,
                duration_ms=duration,
            )
            return True

        log_event(
            "ROUTE_CHANGE_FAILED",
            previous=previous,
            target=target,
            incident_id=incident_id,
        )

        # Restore the previous known configuration,
        # but only when it was a consistent route.
        if previous in ROUTERS:
            rollback_ok = set_routes(previous)
            rollback_verified = (
                rollback_ok and verify_route(previous)
            )

            log_event(
                "ROLLBACK_RESULT",
                target=previous,
                verified=rollback_verified,
                incident_id=incident_id,
            )

        return False

    except Exception as error:
        log_event(
            "ROUTE_CHANGE_EXCEPTION",
            error=str(error),
            incident_id=incident_id,
        )
        return False


# ---------- MONITORING STATE MACHINE ----------

def main():
    failures = 0
    primary_stable = 0
    incident_id = None
    recovery_attempted = False

    log_event(
        "NETPILOT_STARTED",
        active_router=active_router(),
    )

    while True:
        try:
            healthy = connectivity_healthy()
            current = active_router()

            if healthy:
                failures = 0
                recovery_attempted = False

                if incident_id is not None:
                    log_event(
                        "INCIDENT_RESOLVED",
                        incident_id=incident_id,
                        active_router=current,
                    )
                    incident_id = None

                log_event(
                    "NETWORK_HEALTHY",
                    active_router=current,
                )

                # Automatic failback to the primary
                if current == "router-b":
                    if router_usable("router-a"):
                        primary_stable += 1
                    else:
                        primary_stable = 0

                    if primary_stable >= FAILBACK_THRESHOLD:
                        log_event(
                            "PRIMARY_STABLE",
                            checks=primary_stable,
                        )

                        change_router(
                            "router-a",
                            "AUTOMATIC_FAILBACK",
                        )

                        primary_stable = 0
                else:
                    primary_stable = 0

            else:
                failures += 1
                primary_stable = 0

                log_event(
                    "CONNECTIVITY_FAILURE",
                    consecutive_failures=failures,
                    active_router=current,
                )

                if (
                    failures >= FAILURE_THRESHOLD
                    and not recovery_attempted
                ):
                    recovery_attempted = True
                    incident_id = str(uuid.uuid4())

                    log_event(
                        "INCIDENT_CREATED",
                        incident_id=incident_id,
                        active_router=current,
                    )

                    if current == "router-a":
                        change_router(
                            "router-b",
                            "PRIMARY_PATH_FAILURE",
                            incident_id,
                        )
                    else:
                        log_event(
                            "MANUAL_REVIEW_REQUIRED",
                            incident_id=incident_id,
                            reason="No safe automatic action",
                        )

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log_event("NETPILOT_STOPPED")
            break

        except Exception as error:
            log_event(
                "MONITOR_ERROR",
                error=str(error),
            )
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()