import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "agent" / "logs" / "events.jsonl"
STATE_FILE = ROOT / "agent" / "logs" / "aws_forwarder_state.json"
REGION = os.environ.get("NETPILOT_AWS_REGION", "ap-south-1")
QUEUE_NAME = os.environ.get("NETPILOT_SQS_QUEUE", "netpilot-incidents-dev")
POLL_SECONDS = 2
RETRY_SECONDS = 10

# Include the benign synthetic test so we can validate the forwarding pipeline
# before opening Docker. Do NOT forward every NETWORK_HEALTHY or ping failure.
FORWARD_EVENTS = frozenset({
    "CLOUD_PIPELINE_TEST",
    "INCIDENT_CREATED",
    "INCIDENT_RESOLVED",
    "INCIDENT_DEGRADED",
    "FAULT_DIAGNOSED",
    "ROUTE_MISMATCH_DETECTED",
    "RECOVERY_ATTEMPT",
    "RECOVERY_RETRY_SCHEDULED",
    "ROUTE_CHANGE_STARTED",
    "ROUTE_CHANGE_SUCCESS",
    "ROUTE_CHANGE_FAILED",
    "ROUTE_CHANGE_EXCEPTION",
    "ROUTE_UPDATE_ERROR",
    "TARGET_ROUTER_UNAVAILABLE",
    "MANUAL_REVIEW_REQUIRED",
    "ROLLBACK_RESULT",
    "FAILBACK_RESULT",
})


def say(message):
    print(f"[NetPilot AWS Forwarder] {message}", flush=True)


def aws(*args):
    completed = subprocess.run(
        ["aws", *args], capture_output=True, text=True,
        encoding="utf-8", timeout=30, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "AWS CLI command failed")
    return completed.stdout.strip()


def queue_url():
    result = aws(
        "sqs", "get-queue-url", "--queue-name", QUEUE_NAME,
        "--region", REGION, "--query", "QueueUrl", "--output", "text",
    )
    if not result or result == "None":
        raise RuntimeError(f"SQS queue not found: {QUEUE_NAME}")
    return result


def send_event(event, url):
    # v4 creates stable event_id values. Preserve the original payload and ID.
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("Selected event has no valid event_id; delivery paused")
    body = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
    # Windows process command lines have a practical length limit (~32,767 chars).
    if len(body) > 16000:
        raise ValueError("Event is too large for the Windows AWS CLI argument; delivery paused")
    response = json.loads(aws(
        "sqs", "send-message", "--queue-url", url,
        "--message-body", body, "--region", REGION, "--output", "json",
    ))
    if not response.get("MessageId"):
        raise RuntimeError("SQS response was missing MessageId")
    say(f"SENT {event['event']} event_id={event_id} sqs_message_id={response['MessageId']}")


def load_offset():
    if not STATE_FILE.exists():
        return None
    payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    offset = payload.get("offset")
    if not isinstance(offset, int) or offset < 0:
        raise ValueError(f"Invalid offset in {STATE_FILE}")
    return offset


def save_offset(offset):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "offset": offset,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATE_FILE)


def initialize_offset():
    prior = load_offset()
    if prior is not None:
        say(f"Resuming from saved byte offset {prior}")
        return prior
    # Avoid unexpectedly replaying every old incident when installing.
    offset = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    save_offset(offset)
    say(f"First run: starting at END of existing log (offset {offset}). Old events will NOT be resent.")
    return offset


def process_available(offset, url):
    """Process complete new lines. Returns (next_offset, was_successful)."""
    if not LOG_FILE.exists():
        return offset, True

    size = LOG_FILE.stat().st_size
    if size < offset:
        say("Log was truncated/replaced: restarting from byte 0 (duplicates are safe).")
        offset = 0
        save_offset(offset)

    with LOG_FILE.open("rb") as file:
        file.seek(offset)
        while True:
            start = file.tell()
            raw = file.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                # Writer hasn't finished the JSON line yet. Try again next poll.
                break
            end = file.tell()
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                say(f"ERROR malformed JSONL at byte {start}: {error}; keeping checkpoint for inspection")
                return offset, False
            if not isinstance(event, dict):
                say(f"ERROR non-object JSONL at byte {start}; keeping checkpoint for inspection")
                return offset, False
            if event.get("event") in FORWARD_EVENTS:
                try:
                    send_event(event, url)
                except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError) as error:
                    say(f"SEND FAILED for event at byte {start}: {error}. Retrying in {RETRY_SECONDS}s.")
                    return offset, False
            offset = end
            save_offset(offset)
    return offset, True


def main():
    try:
        url = queue_url()
        say(f"Connected to SQS queue={QUEUE_NAME} region={REGION}")
        offset = initialize_offset()
        say(f"Watching {LOG_FILE}; press Ctrl+C to stop")
        while True:
            offset, ok = process_available(offset, url)
            time.sleep(POLL_SECONDS if ok else RETRY_SECONDS)
    except KeyboardInterrupt:
        say("Stopped. Checkpoint retained for next run.")
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        say(f"Startup error: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
