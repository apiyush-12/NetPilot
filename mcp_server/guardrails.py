"""Validation for data returned by NetPilot MCP tools."""
INCIDENT_FIELDS = (
    "created_at",
    "last_event_at",
    "status",
    "fault_type",
    "resolution",
)

def sanitize_incidents(items, limit: int):
    """Return only validated incident summary fields."""

    if not isinstance(items, list) or len(items) > limit:
        raise ValueError("Invalid incident list")

    cleaned = []

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid incident record")

        incident_id = item.get("incident_id")
        event_count = item.get("events")

        if (
            not isinstance(incident_id, str)
            or not 1 <= len(incident_id) <= 128
        ):
            raise ValueError("Invalid incident ID")

        if (
            type(event_count) is not int
            or event_count < 0
        ):
            raise ValueError("Invalid event count")

        record = {
            "incident_id": incident_id,
            "events": event_count,
        }

        for field in INCIDENT_FIELDS:
            value = item.get(field)

            if value is not None and (
                not isinstance(value, str)
                or len(value) > 128
            ):
                raise ValueError(
                    f"Invalid incident field: {field}"
                )

            record[field] = value

        cleaned.append(record)

    return cleaned

EVENT_TEXT_FIELDS = {
    "timestamp", "event_id", "version", "event",
    "incident_id", "active_router", "fault_type",
    "action", "target", "current", "previous",
    "reason", "resolution",
}

EVENT_NUMBER_FIELDS = {
    "attempt", "duration_ms",
}


def sanitize_events(items, incident_id: str, limit: int):
    """Validate incident events before exposing them to AI."""

    if not isinstance(items, list) or len(items) > limit:
        raise ValueError("Invalid event list")
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid event record")

        if item.get("incident_id") != incident_id:
            raise ValueError("Incident ID mismatch")

        if not isinstance(item.get("event"), str) or not item["event"]:
            raise ValueError("Missing event type")

        record = {}

        for field in EVENT_TEXT_FIELDS:
            if field in item:
                value = item[field]

                if (
                    not isinstance(value, str)
                    or len(value) > 256
                ):
                    raise ValueError(
                        f"Invalid event field: {field}"
                    )

                record[field] = value
        for field in EVENT_NUMBER_FIELDS:
            if field in item:
                value = item[field]
                if (
                    type(value) is not int
                    or not 0 <= value <= 1_000_000_000
                ):
                    raise ValueError(
                        f"Invalid numeric field: {field}"
                    )
                record[field] = value
        cleaned.append(record)
    return cleaned