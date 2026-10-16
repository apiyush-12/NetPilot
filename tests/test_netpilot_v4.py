import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from netpilot_v4 import (Controller, Diagnosis, Snapshot, StateStore,
                         classify, ROUTERS, FAILBACK_STABLE_CHECKS)


class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds=35):
        self.value += seconds


class FakeLab:
    def __init__(self):
        self.running = {"client": True, "server": True,
                        "router-a": True, "router-b": True}
        self.forwarding = {"router-a": True, "router-b": True}
        self.client_route = "router-a"
        self.server_route = "router-a"
        self.failed_side = None
        self.failed_once = False
        self.writes = []
        self.force_unhealthy = False
        self.allow_asymmetric_ping = False

    def router_running(self, name):
        return self.running[name]

    def router_forwarding(self, name):
        return self.forwarding[name]

    def router_usable(self, name):
        return (self.running["client"] and self.running["server"]
                and self.running[name] and self.forwarding[name])

    def snapshot(self):
        cr = ROUTERS[self.client_route][0] if self.client_route else None
        sr = ROUTERS[self.server_route][1] if self.server_route else None
        consistent = self.client_route == self.server_route
        both_up = self.running["client"] and self.running["server"]
        if consistent:
            connected = both_up and self.router_usable(self.client_route)
        else:
            connected = (both_up and self.allow_asymmetric_ping
                         and self.router_usable(self.client_route)
                         and self.router_usable(self.server_route))
        return Snapshot(
            self.running["client"], self.running["server"], cr if self.running["client"] else None,
            sr if self.running["server"] else None,
            connected and not self.force_unhealthy,
        )

    def set_route(self, side, router):
        self.writes.append((side, router))
        if self.failed_side == side and not self.failed_once:
            self.failed_once = True
            return False
        if side == "server":
            self.server_route = router
        elif side == "client":
            self.client_route = router
        else:
            raise AssertionError("Unknown side")
        return True


class TestNetPilot(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = FakeClock()
        self.lab = FakeLab()
        self.events = []
        self.store = StateStore(Path(self.temp.name) / "state.json")
        self.controller = Controller(
            self.lab, lambda event, **kw: self.events.append({"event": event, **kw}),
            self.store, clock=self.clock,
        )

    def tick_three(self):
        for _ in range(3):
            self.controller.tick()
            self.clock.advance(5)

    def event(self, name):
        return [e for e in self.events if e["event"] == name]

    def test_healthy_primary_causes_no_route_writes(self):
        self.tick_three()
        self.assertEqual(self.lab.writes, [])
        self.assertEqual(len(self.event("NETWORK_HEALTHY")), 3)
        self.assertIsNone(self.controller.state["incident_id"])

    def test_primary_stopped_fails_over_and_resolves(self):
        self.lab.running["router-a"] = False
        self.tick_three()
        self.assertEqual((self.lab.server_route, self.lab.client_route),
                         ("router-b", "router-b"))
        self.assertEqual(len(self.event("ROUTE_CHANGE_SUCCESS")), 1)
        self.assertEqual(self.event("FAULT_DIAGNOSED")[-1]["fault_type"], "ACTIVE_ROUTER_DOWN")
        self.assertEqual(len(self.event("INCIDENT_RESOLVED")), 1)

    def test_both_routers_down_retries_same_incident(self):
        self.lab.running["router-a"] = False
        self.lab.running["router-b"] = False
        self.tick_three()
        first_id = self.controller.state["incident_id"]
        self.assertIsNotNone(first_id)
        self.assertEqual(self.lab.writes, [])
        self.clock.advance(40)
        self.controller.tick()
        self.assertEqual(self.controller.state["incident_id"], first_id)
        self.assertEqual(self.controller.state["attempts"], 2)
        self.lab.running["router-b"] = True
        self.clock.advance(40)
        self.controller.tick()
        self.assertEqual((self.lab.server_route, self.lab.client_route),
                         ("router-b", "router-b"))
        self.assertIsNone(self.controller.state["incident_id"])
        self.assertEqual(len(self.event("INCIDENT_CREATED")), 1)

    def test_server_down_does_not_change_routes_and_reports_cause(self):
        self.lab.running["server"] = False
        self.tick_three()
        self.assertEqual(self.lab.writes, [])
        self.assertEqual(self.event("FAULT_DIAGNOSED")[-1]["fault_type"], "SERVER_UNAVAILABLE")
        self.assertEqual(len(self.event("MANUAL_REVIEW_REQUIRED")), 1)
        self.assertIsNotNone(self.controller.state["incident_id"])
        self.lab.running["server"] = True
        self.controller.tick()
        self.assertIsNone(self.controller.state["incident_id"])

    def test_unknown_failure_does_not_trigger_a_route_change(self):
        self.lab.force_unhealthy = True
        self.tick_three()
        self.assertEqual(self.lab.writes, [])
        self.assertEqual(self.event("FAULT_DIAGNOSED")[-1]["fault_type"],
                         "UNKNOWN_END_TO_END_FAILURE")

    def test_forwarding_disabled_causes_alternative_failover(self):
        self.lab.forwarding["router-a"] = False
        self.tick_three()
        self.assertEqual(self.event("FAULT_DIAGNOSED")[-1]["fault_type"],
                         "ROUTER_FORWARDING_DISABLED")
        self.assertEqual(self.lab.client_route, "router-b")

    def test_asymmetric_routes_healthy_alert_only(self):
        self.lab.server_route = "router-b"
        self.lab.allow_asymmetric_ping = True
        self.tick_three()
        self.assertEqual(len(self.event("ROUTE_MISMATCH_DETECTED")), 1)
        self.assertEqual(self.lab.writes, [])

    def test_mismatch_with_outage_repairs_both_routes(self):
        self.lab.client_route = "router-a"
        self.lab.server_route = "router-b"
        self.lab.running["router-a"] = False
        self.tick_three()
        self.assertEqual(self.event("FAULT_DIAGNOSED")[-1]["fault_type"], "ROUTE_MISMATCH")
        self.assertEqual(self.lab.client_route, "router-b")
        self.assertEqual(self.lab.server_route, "router-b")

    def test_partial_update_rolls_back_if_previous_is_viable(self):
        self.lab.force_unhealthy = True
        self.lab.failed_side = "client"
        self.tick_three()
        self.assertEqual(self.lab.server_route, "router-a")
        self.assertEqual(self.lab.client_route, "router-a")
        self.assertEqual(len(self.event("ROLLBACK_RESULT")), 0)
        # Unknown failures are alert-only: force the transaction directly.
        self.lab.force_unhealthy = False
        self.controller.switch_router("router-b", "TEST_PARTIAL_FAILURE")
        self.assertEqual(self.lab.server_route, "router-a")
        self.assertEqual(self.lab.client_route, "router-a")
        self.assertEqual(len(self.event("ROLLBACK_RESULT")), 1)
        self.assertTrue(self.event("ROLLBACK_RESULT")[-1]["verified"])

    def test_partial_update_never_rolls_back_to_stopped_router(self):
        self.lab.running["router-a"] = False
        self.lab.failed_side = "client"
        self.assertFalse(self.controller.switch_router("router-b", "TEST_PARTIAL"))
        self.assertEqual(self.lab.server_route, "router-b")
        self.assertEqual(self.lab.client_route, "router-a")
        self.assertEqual(len(self.event("ROLLBACK_SKIPPED")), 1)
        self.assertEqual(len(self.event("MANUAL_REVIEW_REQUIRED")), 1)

    def test_failback_after_stability_checks(self):
        self.lab.client_route = "router-b"
        self.lab.server_route = "router-b"
        for _ in range(FAILBACK_STABLE_CHECKS):
            self.controller.tick()
            self.clock.advance(5)
        self.assertEqual(self.lab.client_route, "router-a")
        self.assertTrue(self.event("FAILBACK_RESULT")[-1]["successful"])

    def test_persists_incident_id_across_controller_restart(self):
        self.lab.running["router-a"] = False
        self.lab.running["router-b"] = False
        self.tick_three()
        incident_id = self.controller.state["incident_id"]
        second = Controller(self.lab, lambda event, **kw: self.events.append({"event": event, **kw}),
                            self.store, clock=self.clock)
        self.assertEqual(second.state["incident_id"], incident_id)
        self.clock.advance(40)
        second.failures = 3  # Simulate detection following a process restart.
        self.lab.running["router-b"] = True
        second.tick()
        self.assertIsNone(second.state["incident_id"])
        self.assertEqual(len(self.event("INCIDENT_CREATED")), 1)


if __name__ == "__main__":
    unittest.main()
