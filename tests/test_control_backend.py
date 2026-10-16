"""Offline tests; no Docker daemon or AWS account is required."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import app as web
from backend import core


class FakeDocker:
    def __init__(self, primary=True, stopped=False):
        self.calls = []
        self.primary = primary
        self.stopped = stopped
        self.fail = False

    def __call__(self, command, **kwargs):
        args = command[4:]  # docker compose -f compose.yaml
        self.calls.append(tuple(args))
        if self.fail:
            return subprocess.CompletedProcess(command, 1, "", "Docker Desktop is not running")
        if args[:4] == ["ps", "-a", "--format", "json"]:
            states = {"client": "running", "server": "running",
                      "router-a": "exited" if self.stopped else "running", "router-b": "running"}
            return subprocess.CompletedProcess(command, 0, "\n".join(json.dumps({
                "Service": k, "State": v, "Status": v
            }) for k, v in states.items()), "")
        if args[:3] == ["exec", "-T", "client"] and "route" in args:
            return subprocess.CompletedProcess(command, 0,
                "10.66.2.10 via 10.66.1.2 dev eth0" if self.primary else "10.66.2.10 via 10.66.1.3 dev eth0", "")
        if args[:3] == ["exec", "-T", "server"] and "route" in args:
            return subprocess.CompletedProcess(command, 0, "10.66.1.10 via 10.66.2.2 dev eth0", "")
        return subprocess.CompletedProcess(command, 0, "", "")


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "lab").mkdir()
        (self.root / "lab" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        self.runner = FakeDocker()
        self.lab = core.Lab(self.root, self.runner)

    def tearDown(self):
        self.temp.cleanup()

    def test_status_healthy_primary(self):
        status = self.lab.status({"controller": False, "forwarder": False})
        self.assertTrue(status["docker_online"])
        self.assertTrue(status["connected"])
        self.assertEqual(status["active_router"], "router-a")

    def test_status_mismatch_without_calling_it_unknown(self):
        self.runner.primary = False
        status = self.lab.status({})
        self.assertEqual(status["active_router"], "mismatch")
        self.assertEqual(status["routes"]["server_gateway"], "10.66.2.2")

    def test_status_offline_is_graceful(self):
        self.runner.fail = True
        status = self.lab.status({})
        self.assertFalse(status["docker_online"])
        self.assertIsNone(status["connected"])

    def test_service_name_and_action_allowlist(self):
        with self.assertRaises(core.ControlError):
            self.lab.service_action("other-project", "stop")
        with self.assertRaises(core.ControlError):
            self.lab.service_action("router-a", "exec")
        self.assertEqual(len(self.runner.calls), 0)

    def test_start_router_uses_explicit_compose_file(self):
        self.lab.service_action("router-a", "start")
        self.assertEqual(self.runner.calls[-1], ("start", "router-a"))

    def test_route_reset_updates_server_before_client(self):
        self.lab.reset_primary_routes()
        writes = [args for args in self.runner.calls if "replace" in args]
        self.assertEqual(writes[0][2], "server")
        self.assertEqual(writes[1][2], "client")

    def test_jsonl_filtering(self):
        path = self.root / "events.jsonl"
        path.write_text('{"event":"INCIDENT_CREATED","incident_id":"a"}\n'
                        '{"event":"INCIDENT_RESOLVED","incident_id":"a"}\n'
                        '{"event":', encoding="utf-8")
        items = core.recent_jsonl(path, event_type="INCIDENT_RESOLVED")
        self.assertEqual(len(items), 1)

    def test_incident_summary_groups_lifecycle(self):
        path = self.root / "events.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in [
            {"event": "INCIDENT_CREATED", "incident_id": "one", "timestamp": "2026-01-01T00:00:00Z"},
            {"event": "FAULT_DIAGNOSED", "incident_id": "one", "fault_type": "ACTIVE_ROUTER_DOWN", "timestamp": "2026-01-01T00:00:01Z"},
            {"event": "INCIDENT_RESOLVED", "incident_id": "one", "timestamp": "2026-01-01T00:00:03Z", "resolution": "AUTOMATED_RECOVERY"},
        ]) + "\n", encoding="utf-8")
        with patch.object(core, "EVENTS", path):
            incidents = core.incident_summary()
        self.assertEqual(incidents[0]["status"], "RESOLVED")
        self.assertEqual(incidents[0]["fault_type"], "ACTIVE_ROUTER_DOWN")

    def test_post_rejects_request_without_control_token(self):
        client = TestClient(web.app)
        with patch.dict(os.environ, {"NETPILOT_CONTROL_TOKEN": "test-only-token"}):
            response = client.post("/api/services/router-a/stop")
        self.assertEqual(response.status_code, 403)

    def test_token_protected_action_calls_whitelisted_command(self):
        client = TestClient(web.app)
        with patch.dict(os.environ, {"NETPILOT_CONTROL_TOKEN": "test-only-token"}):
            with patch.object(web, "lab", self.lab), patch.object(web, "append_audit"):
                response = client.post("/api/services/router-a/stop",
                                       headers={"X-NetPilot-Token": "test-only-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.runner.calls[-1], ("stop", "router-a"))

    def test_status_endpoint_needs_no_running_docker(self):
        client = TestClient(web.app)
        self.runner.fail = True
        with patch.object(web, "lab", self.lab):
            response = client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_router"], "unknown")


if __name__ == "__main__":
    unittest.main()

# Read-only AWS endpoint verifies account services by name without sending credentials.
class CloudTests(unittest.TestCase):
    def test_cloud_status_aggregates_partial_failures(self):
        from backend import cloud
        with patch.object(cloud, "queue_status", side_effect=RuntimeError("AccessDenied")):
            with patch.object(cloud, "query", return_value={"State": "Active"}):
                response = cloud.cloud_status()
        self.assertFalse(response["resources"]["sqs"]["ok"])
        self.assertTrue(response["resources"]["lambda"]["ok"])
