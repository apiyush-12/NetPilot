"""Run with python -m unittest discover -s tests -p test_aws_forwarder.py -v"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "agent" / "aws_forwarder.py"
spec = importlib.util.spec_from_file_location("aws_forwarder", SOURCE)
forwarder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forwarder)


class TestAWSForwarder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.log = self.folder / "events.jsonl"
        self.state = self.folder / "state.json"
        self.patches = [
            patch.object(forwarder, "LOG_FILE", self.log),
            patch.object(forwarder, "STATE_FILE", self.state),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def append(self, event, newline=True):
        with self.log.open("ab") as stream:
            raw = json.dumps(event).encode("utf-8")
            stream.write(raw + (b"\n" if newline else b""))

    def test_first_run_tails_existing_log(self):
        self.append({"event": "INCIDENT_CREATED", "event_id": "old"})
        offset = forwarder.initialize_offset()
        self.assertEqual(offset, self.log.stat().st_size)
        with patch.object(forwarder, "send_event") as send:
            new_offset, success = forwarder.process_available(offset, "test-url")
        self.assertTrue(success)
        self.assertEqual(new_offset, offset)
        send.assert_not_called()

    def test_new_significant_event_is_forwarded_once(self):
        offset = forwarder.initialize_offset()
        event = {"event": "FAULT_DIAGNOSED", "event_id": "one", "fault_type": "ACTIVE_ROUTER_DOWN"}
        self.append(event)
        with patch.object(forwarder, "send_event") as send:
            offset, success = forwarder.process_available(offset, "test-url")
            again, success2 = forwarder.process_available(offset, "test-url")
        self.assertTrue(success and success2)
        self.assertEqual(offset, again)
        send.assert_called_once_with(event, "test-url")
        self.assertEqual(forwarder.load_offset(), offset)

    def test_heartbeats_skipped_but_diagnostic_forwarded(self):
        offset = forwarder.initialize_offset()
        self.append({"event": "NETWORK_HEALTHY", "event_id": "heartbeat"})
        self.append({"event": "FAULT_DIAGNOSED", "event_id": "incident"})
        with patch.object(forwarder, "send_event") as send:
            new_offset, success = forwarder.process_available(offset, "test-url")
        self.assertTrue(success)
        self.assertEqual(new_offset, self.log.stat().st_size)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0]["event_id"], "incident")

    def test_failed_send_is_retried_without_advancing_checkpoint(self):
        offset = forwarder.initialize_offset()
        self.append({"event": "INCIDENT_CREATED", "event_id": "needs-retry"})
        with patch.object(forwarder, "send_event", side_effect=RuntimeError("temporary AWS error")):
            unchanged, success = forwarder.process_available(offset, "test-url")
        self.assertFalse(success)
        self.assertEqual(unchanged, offset)
        self.assertEqual(forwarder.load_offset(), offset)
        with patch.object(forwarder, "send_event") as send:
            advanced, success = forwarder.process_available(offset, "test-url")
        self.assertTrue(success)
        self.assertGreater(advanced, offset)
        send.assert_called_once()

    def test_unfinished_line_is_not_forwarded(self):
        offset = forwarder.initialize_offset()
        self.append({"event": "INCIDENT_CREATED", "event_id": "partial"}, newline=False)
        with patch.object(forwarder, "send_event") as send:
            unchanged, success = forwarder.process_available(offset, "test-url")
        self.assertTrue(success)
        self.assertEqual(unchanged, offset)
        send.assert_not_called()
        with self.log.open("ab") as file:
            file.write(b"\n")
        with patch.object(forwarder, "send_event") as send:
            advanced, success = forwarder.process_available(offset, "test-url")
        self.assertTrue(success)
        self.assertGreater(advanced, offset)
        send.assert_called_once()

    def test_log_truncation_starts_at_zero(self):
        offset = forwarder.initialize_offset()
        self.append({"event": "NETWORK_HEALTHY", "event_id": "a"})
        offset, _ = forwarder.process_available(offset, "test-url")
        self.log.write_bytes(b"{}\n")
        new_offset, success = forwarder.process_available(offset, "test-url")
        self.assertTrue(success)
        self.assertEqual(new_offset, 3)

    def test_malformed_line_preserves_checkpoint(self):
        offset = forwarder.initialize_offset()
        self.log.write_bytes(b"{broken-json\n")
        new_offset, success = forwarder.process_available(offset, "test-url")
        self.assertFalse(success)
        self.assertEqual(new_offset, offset)
        self.assertEqual(forwarder.load_offset(), offset)

    def test_missing_event_id_fails_closed(self):
        offset = forwarder.initialize_offset()
        self.append({"event": "INCIDENT_CREATED"})
        new_offset, success = forwarder.process_available(offset, "test-url")
        self.assertFalse(success)
        self.assertEqual(new_offset, offset)


if __name__ == "__main__":
    unittest.main()
