import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean

LOG_FILE = (
    Path(__file__).resolve().parent
    / "logs"
    / "events.jsonl"
)


def timestamp(event):
    return datetime.fromisoformat(event["timestamp"])


def seconds_between(start, end):
    return round((end - start).total_seconds(), 3)


def analyze():
    if not LOG_FILE.exists():
        print("No event log found.")
        return

    events = [
        json.loads(line)
        for line in LOG_FILE.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    counts = Counter(e["event"] for e in events)

    incidents = {}
    first_failure = None

    for event in events:
        kind = event["event"]

        if kind == "NETWORK_HEALTHY":
            first_failure = None

        elif kind == "CONNECTIVITY_FAILURE":
            if event.get("consecutive_failures") == 1:
                first_failure = timestamp(event)

        elif kind == "INCIDENT_CREATED":
            incidents[event["incident_id"]] = {
                "created": timestamp(event),
                "first_failure": first_failure,
                "failover": None,
                "resolved": None,
            }

        elif kind == "ROUTE_CHANGE_SUCCESS":
            incident_id = event.get("incident_id")
            if incident_id in incidents:
                incidents[incident_id]["failover"] = (
                    timestamp(event)
                )

        elif kind == "INCIDENT_RESOLVED":
            incident_id = event.get("incident_id")
            if incident_id in incidents:
                incidents[incident_id]["resolved"] = (
                    timestamp(event)
                )

    changes = [
        e for e in events
        if e["event"] == "ROUTE_CHANGE_SUCCESS"
    ]

    failovers = [
        e for e in changes
        if e.get("target") == "router-b"
    ]

    failbacks = [
        e for e in changes
        if e.get("target") == "router-a"
    ]

    print("\n========== NETPILOT REPORT ==========")
    print("Events:", len(events))
    print("Incidents:", len(incidents))
    print("Successful failovers:", len(failovers))
    print("Successful failbacks:", len(failbacks))
    print(
        "Failed route changes:",
        counts["ROUTE_CHANGE_FAILED"]
    )

    if changes:
        average = mean(
            e["duration_ms"] for e in changes
        )
        print(
            "Average controller operation:",
            round(average, 2),
            "ms"
        )

    for incident_id, data in incidents.items():
        print("\nIncident:", incident_id)

        if data["resolved"]:
            print("Status: RESOLVED")
            print(
                "Incident duration:",
                seconds_between(
                    data["created"],
                    data["resolved"]
                ),
                "seconds"
            )
        else:
            print("Status: UNRESOLVED")

        if data["first_failure"] and data["failover"]:
            print(
                "First observed failure to failover:",
                seconds_between(
                    data["first_failure"],
                    data["failover"]
                ),
                "seconds"
            )

    print("=====================================\n")


if __name__ == "__main__":
    analyze()