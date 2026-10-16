from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "lab" / "compose.yaml"
LOG_DIR = ROOT / "agent" / "logs"
EVENTS_FILE = LOG_DIR / "events.jsonl"  # Compatible with earlier analytics.
STATE_FILE = LOG_DIR / "controller_state_v4.json"  # Keeps v3 state untouched.

CLIENT_IP, SERVER_IP = "10.66.1.10", "10.66.2.10"
CLIENT_NET, SERVER_NET = "10.66.2.0/24", "10.66.1.0/24"
ROUTERS = {
    "router-a": ("10.66.1.2", "10.66.2.2"),
    "router-b": ("10.66.1.3", "10.66.2.3"),
}

CHECK_INTERVAL_SECONDS = 5
FAILURE_THRESHOLD = 3
RETRY_SECONDS = 30
FAILBACK_STABLE_CHECKS = 6
COMMAND_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class Snapshot:
    client_running: bool
    server_running: bool
    client_gateway: Optional[str]
    server_gateway: Optional[str]
    connected: bool

    def route_name(self) -> str:
        for name, gateways in ROUTERS.items():
            if (self.client_gateway, self.server_gateway) == gateways:
                return name
        return "inconsistent"


@dataclass(frozen=True)
class Diagnosis:
    code: str
    target: Optional[str] = None
    action: str = "ALERT_ONLY"


def classify(snapshot: Snapshot, lab) -> Diagnosis:
    """Diagnose without changing routes. Unknown failures are never guessed."""
    if not snapshot.client_running and not snapshot.server_running:
        return Diagnosis("BOTH_ENDPOINTS_UNAVAILABLE")
    if not snapshot.client_running:
        return Diagnosis("CLIENT_UNAVAILABLE")
    if not snapshot.server_running:
        return Diagnosis("SERVER_UNAVAILABLE")

    current = snapshot.route_name()
    if current == "inconsistent":
        # The forward/return routes disagree. Only repair if we have a verified
        # router to converge on; prefer B if A is down, otherwise prefer A.
        candidates = ("router-a", "router-b")
        for candidate in candidates:
            if lab.router_usable(candidate):
                return Diagnosis("ROUTE_MISMATCH", candidate, "RECONCILE")
        return Diagnosis("ROUTE_MISMATCH_NO_SAFE_TARGET")

    if not lab.router_running(current):
        reason = "ACTIVE_ROUTER_DOWN"
    elif not lab.router_forwarding(current):
        reason = "ROUTER_FORWARDING_DISABLED"
    elif not lab.router_usable(current):
        reason = "ACTIVE_PATH_UNREACHABLE"
    else:
        # Router/path looks fine, yet application connectivity is down.
        # Could be an endpoint service, firewall rule, or transient condition.
        return Diagnosis("UNKNOWN_END_TO_END_FAILURE")

    other = "router-b" if current == "router-a" else "router-a"
    if lab.router_usable(other):
        return Diagnosis(reason, other, "FAILOVER")
    return Diagnosis(reason + "_NO_BACKUP")


class EventLogger:
    def __init__(self, path: Path = EVENTS_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, event: str, **details):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": str(uuid.uuid4()),
            "version": "v4",
            "event": event,
            **details,
        }
        line = json.dumps(record, ensure_ascii=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, flush=True)


class StateStore:
    def __init__(self, path: Path = STATE_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def empty():
        return {"incident_id": None, "status": "HEALTHY", "attempts": 0,
                "next_retry_at": 0.0, "diagnosis": None}

    def load(self):
        if not self.path.exists():
            return self.empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Controller state is not a JSON object")
        state = self.empty()
        for key in state:
            if key in data:
                state[key] = data[key]
        if state["incident_id"] is not None and not isinstance(state["incident_id"], str):
            raise ValueError("Invalid persisted incident ID")
        state["next_retry_at"] = float(state["next_retry_at"])
        state["attempts"] = int(state["attempts"])
        return state

    def save(self, state):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


class DockerLab:
    """The only class allowed to run Docker commands or change lab routes."""
    def __init__(self, compose_file: Path = COMPOSE_FILE):
        self.compose_file = compose_file
        if not self.compose_file.is_file():
            raise FileNotFoundError(f"Compose file missing: {compose_file}")

    def compose(self, *args):
        return subprocess.run(
            ["docker", "compose", "-f", str(self.compose_file), *args],
            capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )

    def run_in(self, service, *args):
        return self.compose("exec", "-T", service, *args)

    def service_running(self, name):
        result = self.compose("ps", "--status", "running", "-q", name)
        if result.returncode != 0:
            raise RuntimeError(f"Docker status check failed for {name}: {result.stderr.strip()}")
        return bool(result.stdout.strip())

    def router_running(self, name):
        return self.service_running(name)

    def router_forwarding(self, name):
        if not self.router_running(name):
            return False
        result = self.run_in(name, "sysctl", "-n", "net.ipv4.ip_forward")
        return result.returncode == 0 and result.stdout.strip() == "1"

    def ping(self, service, address):
        return self.run_in(service, "ping", "-c", "1", "-W", "2", address).returncode == 0

    def gateway(self, service, destination):
        result = self.run_in(service, "ip", "-4", "route", "get", destination)
        if result.returncode != 0:
            raise RuntimeError(f"Cannot inspect route on {service}: {result.stderr.strip()}")
        match = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)\b", result.stdout)
        return match.group(1) if match else None

    def snapshot(self):
        client = self.service_running("client")
        server = self.service_running("server")
        return Snapshot(
            client_running=client,
            server_running=server,
            client_gateway=self.gateway("client", SERVER_IP) if client else None,
            server_gateway=self.gateway("server", CLIENT_IP) if server else None,
            connected=self.ping("client", SERVER_IP) if client and server else False,
        )

    def router_usable(self, name):
        if not self.router_running(name) or not self.router_forwarding(name):
            return False
        client_gateway, server_gateway = ROUTERS[name]
        return (self.ping("client", client_gateway)
                and self.ping(name, SERVER_IP)
                and self.ping("server", server_gateway))

    def set_route(self, side, router):
        client_gateway, server_gateway = ROUTERS[router]
        if side == "server":
            service, network, gateway = "server", SERVER_NET, server_gateway
        elif side == "client":
            service, network, gateway = "client", CLIENT_NET, client_gateway
        else:
            raise ValueError(f"Invalid routing side: {side}")
        result = self.run_in(service, "ip", "route", "replace", network, "via", gateway)
        return result.returncode == 0


class Controller:
    def __init__(self, lab, emit: Callable, store: StateStore,
                 clock: Callable[[], float] = time.time):
        self.lab, self.emit, self.store, self.clock = lab, emit, store, clock
        self.state = store.load()
        self.failures = 0
        self.primary_stable = 0
        self.next_failback_at = 0.0
        self.mismatch_reported = False

    def save(self):
        self.store.save(self.state)

    def resolve(self, snapshot, resolution):
        if self.state["incident_id"] is not None:
            self.emit("INCIDENT_RESOLVED", incident_id=self.state["incident_id"],
                      active_router=snapshot.route_name(), resolution=resolution)
            self.state = StateStore.empty()
            self.save()

    def switch_router(self, target, reason, incident_id=None):
        """A two-sided route transaction with safe, conditional rollback.

        Writes are server-side first, then client-side. A failed transaction
        is *never* rolled back to a router known to be unusable.
        """
        previous_snapshot = self.lab.snapshot()
        previous = previous_snapshot.route_name()
        if not self.lab.router_usable(target):
            self.emit("TARGET_ROUTER_UNAVAILABLE", target=target, incident_id=incident_id)
            return False
        if previous == target:
            return previous_snapshot.connected

        started = time.monotonic()
        self.emit("ROUTE_CHANGE_STARTED", previous=previous, target=target,
                  reason=reason, incident_id=incident_id)
        server_updated = self.lab.set_route("server", target)
        client_updated = self.lab.set_route("client", target) if server_updated else False
        after = self.lab.snapshot()
        verified = after.route_name() == target and after.connected
        if server_updated and client_updated and verified:
            self.emit("ROUTE_CHANGE_SUCCESS", previous=previous, target=target,
                      reason=reason, incident_id=incident_id,
                      duration_ms=round((time.monotonic() - started) * 1000))
            return True

        self.emit("ROUTE_CHANGE_FAILED", previous=previous, target=target,
                  incident_id=incident_id, server_updated=server_updated,
                  client_updated=client_updated, route_after=after.route_name())
        # Only revert to a known healthy, coherent previous path.
        if previous in ROUTERS and self.lab.router_usable(previous):
            restore_server = self.lab.set_route("server", previous)
            restore_client = self.lab.set_route("client", previous) if restore_server else False
            rollback = self.lab.snapshot()
            rollback_ok = (restore_server and restore_client
                           and rollback.route_name() == previous and rollback.connected)
            self.emit("ROLLBACK_RESULT", incident_id=incident_id,
                      target=previous, verified=rollback_ok)
            if not rollback_ok:
                self.emit("MANUAL_REVIEW_REQUIRED", incident_id=incident_id,
                          reason="ROLLBACK_NOT_VERIFIED")
        else:
            self.emit("ROLLBACK_SKIPPED", incident_id=incident_id, previous=previous,
                      reason="Previous route not verified usable")
            self.emit("MANUAL_REVIEW_REQUIRED", incident_id=incident_id,
                      reason="ROUTE_CHANGE_PARTIAL_OR_FAILED")
        return False

    def tick(self):
        snapshot = self.lab.snapshot()
        current = snapshot.route_name()

        if snapshot.connected:
            self.failures = 0
            self.resolve(snapshot, "CONNECTIVITY_RESTORED")
            self.emit("NETWORK_HEALTHY", active_router=current)

            if current == "inconsistent":
                self.primary_stable = 0
                if not self.mismatch_reported:
                    self.emit("ROUTE_MISMATCH_DETECTED", action="ALERT_ONLY",
                              client_gateway=snapshot.client_gateway,
                              server_gateway=snapshot.server_gateway)
                    self.mismatch_reported = True
                return
            self.mismatch_reported = False
            if current == "router-b":
                self.primary_stable = (self.primary_stable + 1
                                       if self.lab.router_usable("router-a") else 0)
                if (self.primary_stable >= FAILBACK_STABLE_CHECKS
                        and self.clock() >= self.next_failback_at):
                    self.emit("PRIMARY_STABLE", checks=self.primary_stable)
                    succeeded = self.switch_router("router-a", "AUTOMATIC_FAILBACK")
                    self.emit("FAILBACK_RESULT", successful=succeeded)
                    self.next_failback_at = self.clock() + RETRY_SECONDS
                    self.primary_stable = 0
            else:
                self.primary_stable = 0
            return

        self.mismatch_reported = False
        self.failures += 1
        self.primary_stable = 0
        self.emit("CONNECTIVITY_FAILURE", consecutive_failures=self.failures,
                  active_router=current)
        if self.failures < FAILURE_THRESHOLD:
            return

        if self.state["incident_id"] is None:
            self.state["incident_id"] = str(uuid.uuid4())
            self.state["status"] = "DEGRADED"
            self.state["attempts"] = 0
            self.state["next_retry_at"] = 0.0
            self.save()
            self.emit("INCIDENT_CREATED", incident_id=self.state["incident_id"],
                      active_router=current)
        if self.clock() < self.state["next_retry_at"]:
            return

        diagnosis = classify(snapshot, self.lab)
        incident_id = self.state["incident_id"]
        self.emit("FAULT_DIAGNOSED", incident_id=incident_id, fault_type=diagnosis.code,
                  action=diagnosis.action, target=diagnosis.target)
        self.state["diagnosis"] = diagnosis.code
        self.state["attempts"] += 1
        self.state["status"] = "RECOVERING" if diagnosis.target else "DEGRADED"
        self.save()

        successful = False
        if diagnosis.action in ("FAILOVER", "RECONCILE") and diagnosis.target:
            self.emit("RECOVERY_ATTEMPT", incident_id=incident_id,
                      attempt=self.state["attempts"], current=current,
                      target=diagnosis.target)
            successful = self.switch_router(diagnosis.target, diagnosis.code, incident_id)
        else:
            self.emit("MANUAL_REVIEW_REQUIRED", incident_id=incident_id,
                      reason=diagnosis.code)

        if successful:
            final = self.lab.snapshot()
            self.emit("INCIDENT_RESOLVED", incident_id=incident_id,
                      active_router=final.route_name(), resolution="AUTOMATED_RECOVERY")
            self.state = StateStore.empty()
            self.save()
            self.failures = 0
        else:
            self.state["status"] = "DEGRADED"
            self.state["next_retry_at"] = self.clock() + RETRY_SECONDS
            self.save()
            self.emit("INCIDENT_DEGRADED", incident_id=incident_id,
                      recovery_attempts=self.state["attempts"],
                      fault_type=diagnosis.code)
            self.emit("RECOVERY_RETRY_SCHEDULED", incident_id=incident_id,
                      delay_seconds=RETRY_SECONDS)


def main():
    logger = EventLogger()
    lab = DockerLab()
    store = StateStore()
    controller = Controller(lab, logger, store)
    logger("NETPILOT_V4_STARTED", pending_incident=controller.state["incident_id"])
    try:
        while True:
            try:
                controller.tick()
            except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
                logger("MONITOR_ERROR", detail=str(error))
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger("NETPILOT_V4_STOPPED", pending_incident=controller.state["incident_id"])


if __name__ == "__main__":
    main()
