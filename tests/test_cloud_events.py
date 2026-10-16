"""Offline tests: never contact AWS or modify a real DynamoDB table."""
import base64
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import app as api
from backend import cloud


class CloudEventTests(unittest.TestCase):
    def test_decode_dynamodb_payload(self):
        value = {"M": {"event": {"S": "FAULT_DIAGNOSED"},
                       "attempt": {"N": "2"}, "duration": {"N": "1.75"},
                       "steps": {"L": [{"S": "detect"}, {"S": "repair"}]},
                       "ok": {"BOOL": True}}}
        parsed = cloud.attribute_value(value)
        self.assertEqual(parsed["attempt"], 2)
        self.assertEqual(parsed["duration"], 1.75)
        self.assertEqual(parsed["steps"], ["detect", "repair"])
        self.assertTrue(parsed["ok"])

    def test_event_page_keeps_original_payload(self):
        row = {
            "event_id": {"S": "evt-1"},
            "event_type": {"S": "FAULT_DIAGNOSED"},
            "timestamp": {"S": "2026-10-15T00:00:00Z"},
            "payload": {"M": {"fault_type": {"S": "ACTIVE_ROUTER_DOWN"}}},
        }
        with patch.object(cloud, "query", return_value={"Items": [row], "Count": 1}):
            data = cloud.cloud_events(limit=50)
        self.assertEqual(data["items"][0]["payload"]["fault_type"], "ACTIVE_ROUTER_DOWN")
        self.assertEqual(data["returned"], 1)
        self.assertIsNone(data["next_cursor"])

    def test_cursor_round_trip_and_rejects_invalid_shape(self):
        key = {"event_id": {"S": "abc"}}
        self.assertEqual(cloud.decode_cursor(cloud.encode_cursor(key)), key)
        with self.assertRaises(ValueError):
            cloud.decode_cursor(base64.urlsafe_b64encode(json.dumps({"role": "admin"}).encode()).decode())
        with self.assertRaises(ValueError):
            cloud.decode_cursor("broken-!")

    def test_next_page_passes_exclusive_start_key(self):
        start = {"event_id": {"S": "evt-1"}}
        with patch.object(cloud, "query", return_value={"Items": [], "Count": 0}) as fn:
            cloud.cloud_events(limit=20, cursor=cloud.encode_cursor(start))
        self.assertIn("--exclusive-start-key", fn.call_args.args)

    def test_count_exact_across_pages(self):
        pages = [
            {"Count": 10, "LastEvaluatedKey": {"event_id": {"S": "item-10"}}},
            {"Count": 11},
        ]
        with patch.object(cloud, "query", side_effect=pages):
            data = cloud.live_item_count(max_pages=2)
        self.assertEqual(data, {"LiveItems": 21, "CountComplete": True})

    def test_partial_count_cannot_masquerade_as_exact(self):
        with patch.object(cloud, "query", return_value={"Count": 250,
            "LastEvaluatedKey": {"event_id": {"S": "more"}}}):
            data = cloud.live_item_count(max_pages=2)
        self.assertIsNone(data["LiveItems"])
        self.assertEqual(data["CountLowerBound"], 500)

    def test_status_retains_delayed_metadata_and_live_count(self):
        with patch.object(cloud, "query", return_value={"Status": "ACTIVE", "ApproximateItems": 0}), \
             patch.object(cloud, "live_item_count", return_value={"LiveItems": 21, "CountComplete": True}):
            data = cloud.table_status()
        self.assertEqual(data["ApproximateItems"], 0)
        self.assertEqual(data["LiveItems"], 21)

    def test_endpoint_read_only_and_validates_limit(self):
        client = TestClient(api.app)
        with patch.object(api, "cloud_events", return_value={"items": [], "next_cursor": None, "returned": 0}):
            response = client.get("/api/cloud/events?limit=50")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/api/cloud/events?limit=101").status_code, 422)

    def test_endpoint_reports_invalid_cursor(self):
        client = TestClient(api.app)
        with patch.object(api, "cloud_events", side_effect=ValueError("Invalid pagination cursor")):
            response = client.get("/api/cloud/events?cursor=invalid")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
