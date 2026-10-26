"""Local audit records for NetPilot AI guardrails."""

import json
from datetime import datetime, timezone
from pathlib import Path


AUDIT_FILE = (
    Path(__file__).resolve().parent
    / "logs"
    / "guardrail_audit.jsonl"
)


def record_audit(
    audit_id: str,
    stage: str,
    status: str,
    reason: str,
    tool_calls=None,
):
    """Save safe audit metadata without questions or answers."""

    AUDIT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    tools = [
        call["tool"]
        for call in (tool_calls or [])
        if isinstance(call, dict)
        and isinstance(call.get("tool"), str)
    ]

    event = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "audit_id": audit_id,
        "stage": stage,
        "status": status,
        "reason": reason,
        "tools": tools,
    }

    with AUDIT_FILE.open(
        "a",
        encoding="utf-8"
    ) as file:
        file.write(json.dumps(event) + "\n")