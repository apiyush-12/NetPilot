"""NetPilot local-only control plane. Strictly predefined Docker operations.

Never expose this service beyond loopback without proper authentication,
authorization, TLS and an agent-hosted remote-control design.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "lab" / "compose.yaml"
LOG_DIR = ROOT / "agent" / "logs"
EVENTS = LOG_DIR / "events.jsonl"
AUDIT = LOG_DIR / "control_actions.jsonl"
CONTROLLER = ROOT / "agent" / "netpilot_v4.py"
FORWARDER = ROOT / "agent" / "aws_forwarder.py"
SERVICES = frozenset({"client", "server", "router-a", "router-b"})
ROUTERS = {"router-a": ("10.66.1.2", "10.66.2.2"), "router-b": ("10.66.1.3", "10.66.2.3")}
SCRIPTS = {"controller": CONTROLLER, "forwarder": FORWARDER}


class ControlError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_audit(action: str, target: str, outcome: str, detail: str = "") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": utc_now(), "action": action, "target": target,
              "outcome": outcome, "detail": detail[:400]}
    with AUDIT.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def recent_jsonl(path: Path, limit: int = 50, event_type: str | None = None,
                 incident_id: str | None = None) -> list[dict[str, Any]]:
    """Bounded-memory reader; tolerant of an incomplete last line."""
    if not path.is_file():
        return []
    found: deque[dict[str, Any]] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if event_type and obj.get("event") != event_type:
                continue
            if incident_id and obj.get("incident_id") != incident_id:
                continue
            found.append(obj)
    return list(found)


def incident_summary(limit: int = 100) -> list[dict[str, Any]]:
    """Derive incident timelines from v4 JSONL events, newest first."""
    events = recent_jsonl(EVENTS, limit=20000)
    summaries: dict[str, dict[str, Any]] = {}
    for event in events:
        incident_id = event.get("incident_id")
        if not isinstance(incident_id, str) or not incident_id:
            continue
        entry = summaries.setdefault(incident_id, {
            "incident_id": incident_id, "created_at": None,
            "last_event_at": None, "status": "OPEN", "fault_type": None,
            "events": 0, "resolution": None,
        })
        entry["events"] += 1
        entry["last_event_at"] = event.get("timestamp")
        if event.get("event") == "INCIDENT_CREATED":
            entry["created_at"] = event.get("timestamp")
        elif event.get("event") == "FAULT_DIAGNOSED":
            entry["fault_type"] = event.get("fault_type")
        elif event.get("event") == "INCIDENT_RESOLVED":
            entry["status"] = "RESOLVED"
            entry["resolution"] = event.get("resolution")
    return sorted(summaries.values(), key=lambda item: item["last_event_at"] or "", reverse=True)[:limit]


class Lab:
    def __init__(self, root: Path = ROOT, runner=None):
        self.root = Path(root)
        self.compose_file = self.root / "lab" / "compose.yaml"
        self.runner = runner or subprocess.run
        self.lock = threading.RLock()

    def command(self, *args: str, timeout: int = 20):
        if not self.compose_file.exists():
            raise ControlError(f"Compose file not found: {self.compose_file}")
        try:
            result = self.runner(
                ["docker", "compose", "-f", str(self.compose_file), *args],
                capture_output=True, text=True, timeout=timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ControlError(f"Docker command unavailable or timed out: {error}") from error
        if result.returncode != 0:
            raise ControlError((result.stderr or result.stdout or "Docker command failed").strip()[:1000])
        return result.stdout

    def service_states(self) -> dict[str, dict[str, Any]]:
        """Compose --format json may output an array or JSON Lines."""
        raw = self.command("ps", "-a", "--format", "json")
        records: list[dict] = []
        if raw.strip():
            try:
                parsed = json.loads(raw)
                records = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                records = [json.loads(line) for line in raw.splitlines() if line.strip()]
        state: dict[str, dict[str, Any]] = {
            name: {"state": "absent", "running": False, "status": "Not created"}
            for name in sorted(SERVICES)
        }
        for item in records:
            name = item.get("Service")
            if name in SERVICES:
                current = str(item.get("State", "unknown")).lower()
                state[name] = {"state": current, "running": current == "running",
                               "status": item.get("Status", "")}
        return state

    def exec(self, service: str, *args: str) -> str:
        if service not in SERVICES:
            raise ControlError("Service is not allowed")
        return self.command("exec", "-T", service, *args)

    def gateway(self, service: str, destination: str) -> str | None:
        output = self.exec(service, "ip", "-4", "route", "get", destination)
        match = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)\b", output)
        return match.group(1) if match else None

    def router_diagnostics(self, router: str) -> dict[str, Any]:
            """Read router status without modifying configuration."""

            if router not in ROUTERS:
                raise ControlError("Unsupported router")

            states = self.service_states()
            running = states[router]["running"]

            client_ip, server_ip = ROUTERS[router]

            result = {
                "router": router,
                "running": running,
                "ip_forwarding": None,
                "expected_addresses": {
                    "client_side": client_ip,
                    "server_side": server_ip,
                },
                "diagnostic_errors": [],
            }

            if not running:
                return result

            try:
                value = self.exec(
                    router,
                    "sysctl",
                    "-n",
                    "net.ipv4.ip_forward"
                ).strip()

                if value in ("0", "1"):
                    result["ip_forwarding"] = value == "1"
                else:
                    result["diagnostic_errors"].append(
                        "Unexpected IP forwarding value"
                    )

            except ControlError as error:
                result["diagnostic_errors"].append(str(error))

            return result

    def status(self, jobs: dict[str, bool]) -> dict[str, Any]:
        try:
            services = self.service_states()
        except (ControlError, ValueError) as error:
            return {"docker_online": False, "error": str(error), "services": {},
                    "routes": None, "active_router": "unknown", "connected": None,
                    "processes": jobs, "timestamp": utc_now()}
        client = services["client"]["running"]
        server = services["server"]["running"]
        route_data: dict[str, Any] = {"client_gateway": None, "server_gateway": None}
        errors = []
        if client:
            try:
                route_data["client_gateway"] = self.gateway("client", "10.66.2.10")
            except ControlError as error:
                errors.append("client: " + str(error))
        if server:
            try:
                route_data["server_gateway"] = self.gateway("server", "10.66.1.10")
            except ControlError as error:
                errors.append("server: " + str(error))
        current = "unknown"
        if client and server and not errors:
            current = "mismatch"
            for router, gateways in ROUTERS.items():
                if (route_data["client_gateway"], route_data["server_gateway"]) == gateways:
                    current = router
        reachable = None
        if client and server:
            try:
                self.exec("client", "ping", "-c", "1", "-W", "2", "10.66.2.10")
                reachable = True
            except ControlError:
                reachable = False
        return {"docker_online": True, "services": services, "routes": route_data,
                "route_errors": errors, "active_router": current, "connected": reachable,
                "processes": jobs, "timestamp": utc_now()}

    def service_action(self, service: str, action: str) -> None:
        if service not in SERVICES or action not in {"start", "stop", "restart"}:
            raise ControlError("Unsupported service or action")
        with self.lock:
            self.command(action, service, timeout=60)

    def lab_action(self, action: str) -> None:
        if action not in {"start", "stop"}:
            raise ControlError("Unsupported lab action")
        with self.lock:
            self.command(action, timeout=90)

    def reset_primary_routes(self) -> None:
        """Intended only while controller stopped; restore known lab default."""
        with self.lock:
            states = self.service_states()
            if not (states["client"]["running"] and states["server"]["running"] and
                    states["router-a"]["running"]):
                raise ControlError("Client, server and Router A must be running")
            self.exec("server", "ip", "route", "replace", "10.66.1.0/24", "via", "10.66.2.2")
            self.exec("client", "ip", "route", "replace", "10.66.2.0/24", "via", "10.66.1.2")
            after = self.status({})
            if after["active_router"] != "router-a" or not after["connected"]:
                raise ControlError("Route reset not verified; inspect routes manually")


class ProcessSupervisor:
    """Supervises only children launched by this API server instance."""
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.lock = threading.RLock()
        self.processes: dict[str, subprocess.Popen] = {}
        self.handles: dict[str, Any] = {}

    def running(self, name: str) -> bool:
        with self.lock:
            proc = self.processes.get(name)
            return proc is not None and proc.poll() is None

    def status(self) -> dict[str, bool]:
        return {name: self.running(name) for name in SCRIPTS}

    def start(self, name: str) -> int:
        if name not in SCRIPTS:
            raise ControlError("Unknown managed process")
        with self.lock:
            if self.running(name):
                raise ControlError(f"{name} is already running")
            script = self.root / "agent" / SCRIPTS[name].name
            if not script.exists():
                raise ControlError(f"Missing script: {script}")
            log_dir = self.root / "agent" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            previous = self.handles.pop(name, None)
            if previous:
                previous.close()
            handle = (log_dir / f"{name}_console.log").open("a", encoding="utf-8")
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-u", str(script)], cwd=str(self.root),
                    stdout=handle, stderr=subprocess.STDOUT,
                    creationflags=flags,
                    **({"start_new_session": True} if os.name != "nt" else {}),
                )
            except OSError as error:
                handle.close()
                raise ControlError(f"Cannot start {name}: {error}") from error
            self.processes[name] = proc
            self.handles[name] = handle
            return proc.pid

    def stop(self, name: str) -> None:
        if name not in SCRIPTS:
            raise ControlError("Unknown managed process")
        with self.lock:
            proc = self.processes.get(name)
            if proc is None or proc.poll() is not None:
                raise ControlError(f"{name} is not running under this backend")
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(proc.pid, signal.SIGINT)
                proc.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=4)
            handle = self.handles.pop(name, None)
            if handle:
                handle.close()

    def close(self) -> None:
        for name in SCRIPTS:
            if self.running(name):
                try:
                    self.stop(name)
                except ControlError:
                    pass
        for handle in self.handles.values():
            handle.close()
        self.handles.clear()
