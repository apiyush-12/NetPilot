"""Read-only NetPilot AWS status and DynamoDB event explorer.

AWS CLI credentials remain on the machine running FastAPI. No secret is returned
in responses. These endpoints are intended for loopback development only.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import subprocess
from datetime import datetime, timezone

REGION = os.environ.get("NETPILOT_AWS_REGION", "ap-south-1")
QUEUE = "netpilot-incidents-dev"
DLQ = "netpilot-incidents-dlq-dev"
LAMBDA = "netpilot-incident-processor-dev"
TABLE = "netpilot-events-dev"
ALARM = "netpilot-dlq-alert-dev"


def query(*args):
    try:
        result = subprocess.run(
            ["aws", *args, "--region", REGION, "--output", "json"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"AWS CLI unavailable or timed out: {error}") from error
    if result.returncode:
        raise RuntimeError((result.stderr or "AWS command failed").strip()[:500])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("AWS returned invalid JSON") from error


def queue_status(name):
    info = query("sqs", "get-queue-url", "--queue-name", name)
    attrs = query(
        "sqs", "get-queue-attributes", "--queue-url", info["QueueUrl"],
        "--attribute-names", "ApproximateNumberOfMessages",
        "ApproximateNumberOfMessagesNotVisible",
    )
    values = attrs.get("Attributes", {})
    return {
        "available_messages": int(values.get("ApproximateNumberOfMessages", 0)),
        "in_flight_messages": int(values.get("ApproximateNumberOfMessagesNotVisible", 0)),
    }


def _scan_args(*, limit, start_key=None, count_only=False):
    args = ["dynamodb", "scan", "--table-name", TABLE,
            "--limit", str(limit), "--consistent-read", "--no-paginate"]
    if count_only:
        args += ["--select", "COUNT"]
    if start_key is not None:
        args += ["--exclusive-start-key", json.dumps(start_key, separators=(",", ":"))]
    return args


def _valid_key(key):
    return (isinstance(key, dict) and set(key) == {"event_id"}
            and isinstance(key["event_id"], dict)
            and set(key["event_id"]) == {"S"}
            and isinstance(key["event_id"]["S"], str)
            and bool(key["event_id"]["S"]))


def encode_cursor(key):
    if not _valid_key(key):
        raise ValueError("Unexpected DynamoDB continuation key")
    data = json.dumps(key, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def decode_cursor(cursor):
    if not isinstance(cursor, str) or len(cursor) > 2048:
        raise ValueError("Invalid pagination cursor")
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        key = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid pagination cursor") from error
    if not _valid_key(key):
        raise ValueError("Invalid pagination cursor")
    return key


def attribute_value(value):
    """Decode the DynamoDB CLI AttributeValue shape for display."""
    if not isinstance(value, dict):
        return None
    if "S" in value:
        return value["S"]
    if "N" in value:
        raw = value["N"]
        try:
            return int(raw) if raw.lstrip("-").isdigit() else float(raw)
        except (ValueError, TypeError):
            return raw
    if "BOOL" in value:
        return bool(value["BOOL"])
    if "NULL" in value:
        return None
    if "M" in value:
        return {key: attribute_value(v) for key, v in value["M"].items()}
    if "L" in value:
        return [attribute_value(v) for v in value["L"]]
    if "SS" in value:
        return value["SS"]
    if "NS" in value:
        return [attribute_value({"N": n}) for n in value["NS"]]
    return None


def cloud_events(limit=50, cursor=None):
    """Read one bounded DynamoDB scan page; return a cursor for the next page.

    DynamoDB Scan is not globally timestamp-sorted. The client may sort the
    currently loaded records. A future source/timestamp GSI enables ordered Query.
    """
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Limit must be from 1 to 100")
    start = decode_cursor(cursor) if cursor else None
    response = query(*_scan_args(limit=limit, start_key=start))
    items = []
    for raw in response.get("Items", []):
        item = {k: attribute_value(v) for k, v in raw.items()}
        if item.get("event_id"):
            items.append(item)
    items.sort(key=lambda i: (i.get("timestamp") or "", i.get("event_id") or ""), reverse=True)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": items,
        "next_cursor": encode_cursor(next_key) if next_key else None,
        "returned": len(items),
        "note": "Timestamp ordering applies to the loaded page, not the entire DynamoDB table.",
    }


def live_item_count(max_pages=10, page_limit=250):
    """Count a bounded number of pages; never call partial counts exact."""
    count, key = 0, None
    for _ in range(max_pages):
        result = query(*_scan_args(limit=page_limit, start_key=key, count_only=True))
        count += int(result["Count"])
        key = result.get("LastEvaluatedKey")
        if not key:
            return {"LiveItems": count, "CountComplete": True}
        if not _valid_key(key):
            raise RuntimeError("Invalid continuation key from DynamoDB")
    return {"LiveItems": None, "CountComplete": False, "CountLowerBound": count}


def table_status():
    data = query(
        "dynamodb", "describe-table", "--table-name", TABLE,
        "--query", "{Status:Table.TableStatus,ApproximateItems:Table.ItemCount}",
    )
    # Metadata still remains useful, even if live count permission is denied.
    try:
        data.update(live_item_count())
    except (RuntimeError, ValueError, KeyError, TypeError) as error:
        data["LiveItems"] = None
        data["LiveCountError"] = str(error)
    return data


def cloud_status():
    output = {
        "region": REGION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "resources": {},
        "note": "SQS counts are approximate; DynamoDB live count is a bounded scan.",
    }
    resources = {
        "sqs": lambda: queue_status(QUEUE),
        "dead_letter_queue": lambda: queue_status(DLQ),
        "lambda": lambda: query(
            "lambda", "get-function-configuration", "--function-name", LAMBDA,
            "--query", "{State:State,LastUpdateStatus:LastUpdateStatus,Runtime:Runtime}",
        ),
        "dynamodb": table_status,
        "dlq_alarm": lambda: query(
            "cloudwatch", "describe-alarms", "--alarm-names", ALARM,
            "--query", "MetricAlarms[0].{State:StateValue,Name:AlarmName}",
        ),
    }
    for name, getter in resources.items():
        try:
            output["resources"][name] = {"ok": True, "data": getter()}
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            output["resources"][name] = {"ok": False, "error": str(error)}
    return output
