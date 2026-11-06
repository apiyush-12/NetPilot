"""NetPilot Resilience Lab: controlled Docker fault experiments."""

import json
from typing import Literal
from uuid import uuid4
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.core import (
    ControlError,
    Lab,
    LOG_DIR,
    ProcessSupervisor,
    append_audit,
    utc_now,
    EVENTS,
    recent_jsonl,
    incident_summary,
)


HISTORY = LOG_DIR / "resilience_experiments.jsonl"


class InjectionRequest(BaseModel):
    confirmation: Literal["INJECT"]

# Phase 3: Read-only recovery measurements

EXPECTED_FAULTS = {
    "route_mismatch": "ROUTE_MISMATCH",
    "primary_router_failure": "ACTIVE_ROUTER_DOWN",
}


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        return result if result.tzinfo else None
    except ValueError:
        return None


def elapsed_ms(start, end):
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() * 1000)


def measure_experiment(record, events, next_injection=None):
    start = parse_time(record.get("injected_at"))
    expected = EXPECTED_FAULTS.get(record.get("scenario"))

    base = {
        "experiment_id": record.get("experiment_id"),
        "scenario": record.get("scenario"),
        "injected_at": record.get("injected_at"),
        "incident_id": None,
        "correlation": "timestamp_and_fault_type",
        "status": "NO_MATCHING_INCIDENT",
        "verified_recovery": False,
        "metrics": {
            "first_failure_ms": None,
            "incident_created_ms": None,
            "incident_recovery_ms": None,
            "total_recovery_ms": None,
            "route_change_ms": None,
        },
    }

    if start is None or expected is None:
        return base

    # Correlate only within a bounded experiment window.
    end = start + timedelta(minutes=5)
    next_time = parse_time(next_injection)
    if next_time is not None and next_time > start:
        end = min(end, next_time)

    window = []
    for event in events:
        when = parse_time(event.get("timestamp"))
        if when is not None and start <= when < end:
            window.append((when, event))

    window.sort(key=lambda item: item[0])

    # Find an incident whose diagnosis matches this scenario.
    matched = None

    for created_at, event in window:
        if event.get("event") != "INCIDENT_CREATED":
            continue

        incident_id = event.get("incident_id")
        if not incident_id:
            continue

        related = [
            (when, item)
            for when, item in window
            if item.get("incident_id") == incident_id
            and when >= created_at
        ]

        diagnosed = any(
            item.get("event") == "FAULT_DIAGNOSED"
            and item.get("fault_type") == expected
            for _, item in related
        )

        if diagnosed:
            matched = (created_at, incident_id, related)
            break

    if matched is None:
        return base

    created_at, incident_id, related = matched

    failures = [
        when for when, item in window
        if item.get("event") == "CONNECTIVITY_FAILURE"
        and when <= created_at
    ]

    resolved = next(
        (
            when for when, item in related
            if item.get("event") == "INCIDENT_RESOLVED"
        ),
        None,
    )

    route_change = next(
        (
            item for _, item in related
            if item.get("event") == "ROUTE_CHANGE_SUCCESS"
        ),
        None,
    )

    verified = resolved is not None and route_change is not None

    if verified:
        status = "RECOVERED"
    elif resolved is not None:
        status = "RESOLVED_NO_REPAIR_EVIDENCE"
    else:
        status = "INCIDENT_OPEN"

    base.update({
        "incident_id": incident_id,
        "status": status,
        "verified_recovery": verified,
        "metrics": {
            "first_failure_ms": elapsed_ms(
                start, failures[0] if failures else None
            ),
            "incident_created_ms": elapsed_ms(
                start, created_at
            ),
            "incident_recovery_ms": elapsed_ms(
                created_at, resolved
            ),
            "total_recovery_ms": elapsed_ms(
                start, resolved
            ),
            "route_change_ms": (
                route_change.get("duration_ms")
                if route_change else None
            ),
        },
    })

    return base

# Phase 4: Historical incident replay

REPLAY_EVENTS = {
    "CONNECTIVITY_FAILURE": (
        "DETECTION", "Connectivity check failed"
    ),
    "INCIDENT_CREATED": (
        "INCIDENT", "Incident created"
    ),
    "FAULT_DIAGNOSED": (
        "DIAGNOSIS", "Fault diagnosed"
    ),
    "RECOVERY_ATTEMPT": (
        "RECOVERY", "Recovery attempt started"
    ),
    "ROUTE_CHANGE_STARTED": (
        "RECOVERY", "Route change started"
    ),
    "ROUTE_CHANGE_SUCCESS": (
        "RECOVERY", "Route change verified"
    ),
    "ROUTE_CHANGE_FAILED": (
        "RECOVERY", "Route change failed"
    ),
    "TARGET_ROUTER_UNAVAILABLE": (
        "RECOVERY", "Target router unavailable"
    ),
    "ROLLBACK_RESULT": (
        "RECOVERY", "Rollback result"
    ),
    "ROLLBACK_SKIPPED": (
        "RECOVERY", "Rollback skipped"
    ),
    "RECOVERY_RETRY_SCHEDULED": (
        "RECOVERY", "Retry scheduled"
    ),
    "INCIDENT_DEGRADED": (
        "INCIDENT", "Incident remains degraded"
    ),
    "MANUAL_REVIEW_REQUIRED": (
        "ESCALATION", "Manual review required"
    ),
    "INCIDENT_RESOLVED": (
        "RESOLUTION", "Incident resolved"
    ),
}

REPLAY_FIELDS = (
    "consecutive_failures",
    "active_router",
    "fault_type",
    "action",
    "target",
    "current",
    "previous",
    "attempt",
    "reason",
    "duration_ms",
    "resolution",
    "verified",
    "recovery_attempts",
    "delay_seconds",
)


def build_experiment_replay(
    record, events, next_injection=None
):
    outcome = measure_experiment(
        record, events, next_injection
    )

    start = parse_time(record.get("injected_at"))

    replay = {
        "experiment_id": record.get("experiment_id"),
        "scenario": record.get("scenario"),
        "incident_id": outcome["incident_id"],
        "status": outcome["status"],
        "verified_recovery": outcome["verified_recovery"],
        "metrics": outcome["metrics"],
        "baseline": record.get("baseline"),
        "replay_mode": "READ_ONLY",
        "timeline": [],
        "truncated": False,
    }

    if start is None:
        return replay

    # This step comes from the experiment record.
    replay["timeline"].append({
        "event": "FAULT_INJECTED",
        "phase": "INJECTION",
        "label": "Controlled fault injected",
        "timestamp": record["injected_at"],
        "elapsed_ms": 0,
        "source": "experiment_log",
        "association": "experiment_id",
        "details": {
            "scenario": record.get("scenario")
        },
    })

    incident_id = outcome["incident_id"]

    if not incident_id:
        return replay

    end = start + timedelta(minutes=5)
    next_time = parse_time(next_injection)

    if next_time is not None and next_time > start:
        end = min(end, next_time)

    related = []

    # Match incident events using the real incident ID.
    for event in events:
        when = parse_time(event.get("timestamp"))

        if when is None or not (start <= when < end):
            continue

        if (
            event.get("incident_id") == incident_id
            and event.get("event") in REPLAY_EVENTS
        ):
            related.append((when, event, False))

    # Find when the matching incident was created.
    created_at = next(
        (
            when
            for when, event, _ in sorted(
                related, key=lambda item: item[0]
            )
            if event.get("event") == "INCIDENT_CREATED"
        ),
        None,
    )

    # Early failure events have no incident ID.
    # Associate them by the experiment time window.
    if created_at is not None:
        for event in events:
            if event.get("event") != "CONNECTIVITY_FAILURE":
                continue

            when = parse_time(event.get("timestamp"))

            if when is not None and start <= when <= created_at:
                related.append((when, event, True))

    related.sort(key=lambda item: item[0])

    for when, event, approximate in related[:150]:
        phase, label = REPLAY_EVENTS[event["event"]]

        replay["timeline"].append({
            "event": event["event"],
            "phase": phase,
            "label": label,
            "timestamp": event["timestamp"],
            "elapsed_ms": elapsed_ms(start, when),
            "source": "controller_log",
            "association": (
                "time_window" if approximate
                else "incident_id"
            ),
            "details": {
                field: event[field]
                for field in REPLAY_FIELDS
                if field in event
                and event[field] is not None
            },
        })

    replay["truncated"] = len(related) > 150

    return replay

def create_resilience_router(
    lab: Lab,
    supervisor: ProcessSupervisor,
    require_token,
) -> APIRouter:

    router = APIRouter(
        prefix="/api/resilience",
        tags=["Resilience Lab"],
    )

    @router.get("/scenarios")
    def list_scenarios():
        return {
            "items": [
                {
                    "id": "route_mismatch",
                    "name": "Route Mismatch",
                    "description": "Inject an invalid client gateway.",
                    "target": "client",
                },
                {
                    "id": "primary_router_failure",
                    "name": "Primary Router Failure",
                    "description": "Stop Router A in the Docker lab.",
                    "target": "router-a",
                },
            ],
            "injection_enabled": True,
        }

    @router.get("/readiness")
    def check_readiness():
        status = lab.status(supervisor.status())
        services = status.get("services") or {}

        checks = {
            "docker_online": status.get("docker_online") is True,
            "nodes_running": all(
                services.get(node, {}).get("running") is True
                for node in ("client", "server", "router-a", "router-b")
            ),
            "connectivity_ok": status.get("connected") is True,
            "controller_managed": supervisor.running("controller"),
            "primary_path_active": status.get("active_router") == "router-a",
        }

        return {
            "ready": all(checks.values()),
            "checks": checks,
            "active_router": status.get("active_router"),
        }

    @router.post(
        "/inject/{scenario}",
        dependencies=[Depends(require_token)],
    )
    def inject_fault(
        scenario: Literal["route_mismatch", "primary_router_failure"],
        request: InjectionRequest,
    ):
        try:
            with lab.lock:
                status = lab.status(supervisor.status())
                services = status.get("services") or {}

                if not supervisor.running("controller"):
                    raise ControlError(
                        "Start the managed controller before injection"
                    )

                if not status.get("docker_online"):
                    raise ControlError("Docker lab is offline")

                if not all(
                    services.get(node, {}).get("running") is True
                    for node in ("client", "server", "router-a", "router-b")
                ):
                    raise ControlError(
                        "All four Docker nodes must be running"
                    )

                if status.get("connected") is not True:
                    raise ControlError(
                        "Network must be healthy before injection"
                    )

                if status.get("active_router") != "router-a":
                    raise ControlError(
                        "Start the experiment on Router A"
                    )

                if scenario == "primary_router_failure":
                    backup = lab.router_diagnostics("router-b")

                    if backup.get("ip_forwarding") is not True:
                        raise ControlError(
                            "Router B must have IP forwarding enabled"
                        )

                    # Check that the backup router is locally reachable.
                    lab.exec(
                        "client", "ping", "-c", "1", "-W", "2",
                        "10.66.1.3",
                    )
                    lab.exec(
                        "server", "ping", "-c", "1", "-W", "2",
                        "10.66.2.3",
                    )

                experiment_id = str(uuid4())
                started_at = utc_now()

                if scenario == "route_mismatch":
                    lab.exec(
                        "client",
                        "ip", "route", "replace",
                        "10.66.2.0/24",
                        "via", "10.66.1.254",
                    )
                else:
                    lab.service_action("router-a", "stop")

                injected_at = utc_now()

                record = {
                    "experiment_id": experiment_id,
                    "scenario": scenario,
                    "started_at": started_at,
                    "injected_at": injected_at,
                    "status": "INJECTED",
                    "baseline": {
                        "connected": status["connected"],
                        "active_router": status["active_router"],
                        "routes": status.get("routes"),
                    },
                }

                HISTORY.parent.mkdir(parents=True, exist_ok=True)

                with HISTORY.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record) + "\n")

        except ControlError as error:
            append_audit(
                "resilience-inject", scenario, "ERROR", str(error)
            )
            raise HTTPException(
                status_code=409,
                detail=str(error),
            ) from error

        except OSError as error:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Experiment recording failed. The fault may "
                    "already be active; inspect the lab before retrying."
                ),
            ) from error

        append_audit(
            "resilience-inject",
            scenario,
            "SUCCESS",
            experiment_id,
        )

        return {
            "ok": True,
            **record,
            "message": "Fault injected; recovery is handled by the controller.",
        }

# Phase 3: Experiment measurement APIs

    @router.get("/experiments")
    def list_experiments(
        limit: int = Query(10, ge=1, le=50)
    ):
        records = recent_jsonl(HISTORY, limit=20000)
        events = recent_jsonl(EVENTS, limit=20000)

        records.sort(
            key=lambda item: item.get("injected_at") or ""
        )

        results = []

        for index in range(len(records) - 1, -1, -1):
            record = records[index]

            next_injection = (
                records[index + 1].get("injected_at")
                if index + 1 < len(records)
                else None
            )

            results.append(
                measure_experiment(
                    record, events, next_injection
                )
            )

            if len(results) >= limit:
                break

        return {"items": results}

    @router.get("/experiments/{experiment_id}")
    def get_experiment(experiment_id: UUID):
        records = recent_jsonl(HISTORY, limit=20000)
        events = recent_jsonl(EVENTS, limit=20000)

        records.sort(
            key=lambda item: item.get("injected_at") or ""
        )

        for index, record in enumerate(records):
            if record.get("experiment_id") != str(experiment_id):
                continue

            next_injection = (
                records[index + 1].get("injected_at")
                if index + 1 < len(records)
                else None
            )

            return measure_experiment(
                record, events, next_injection
            )

        raise HTTPException(
            status_code=404,
            detail="Experiment not found",
        )

# Phase 4: Historical experiment replay

    @router.get("/experiments/{experiment_id}/replay")
    def replay_experiment(experiment_id: UUID):
        records = recent_jsonl(
            HISTORY, limit=20000
        )
        events = recent_jsonl(
            EVENTS, limit=20000
        )

        records.sort(
            key=lambda item: item.get("injected_at") or ""
        )

        for index, record in enumerate(records):
            if record.get("experiment_id") != str(experiment_id):
                continue

            next_injection = (
                records[index + 1].get("injected_at")
                if index + 1 < len(records)
                else None
            )

            return build_experiment_replay(
                record,
                events,
                next_injection,
            )

        raise HTTPException(
            status_code=404,
            detail="Experiment not found",
        )

# Phase 5A: Unified resilience history

    @router.get("/history")
    def get_resilience_history(
        limit: int = Query(50, ge=1, le=100)
    ):
        records = recent_jsonl(HISTORY, limit=20000)
        events = recent_jsonl(EVENTS, limit=20000)

        records.sort(
            key=lambda item: item.get("injected_at") or ""
        )

        history = []
        linked_incidents = set()

        # Controlled experiments
        for index, record in enumerate(records):
            next_injection = (
                records[index + 1].get("injected_at")
                if index + 1 < len(records)
                else None
            )

            result = measure_experiment(
                record, events, next_injection
            )

            incident_id = result.get("incident_id")

            if incident_id:
                linked_incidents.add(incident_id)

            history.append({
                "id": f"experiment:{record['experiment_id']}",
                "kind": "experiment",
                "experiment_id": record["experiment_id"],
                "incident_id": incident_id,
                "scenario": record["scenario"],
                "fault_type": None,
                "status": result["status"],
                "timestamp": record["injected_at"],
                "correlation": result["correlation"],
            })

        # Incidents not linked to a recorded experiment
        for incident in incident_summary(limit=200):
            incident_id = incident["incident_id"]

            if incident_id in linked_incidents:
                continue

            history.append({
                "id": f"incident:{incident_id}",
                "kind": "observed",
                "experiment_id": None,
                "incident_id": incident_id,
                "scenario": None,
                "fault_type": incident.get("fault_type"),
                "status": incident["status"],
                "timestamp": (
                    incident.get("created_at")
                    or incident.get("last_event_at")
                ),
                "correlation": "incident_id",
            })

        history.sort(
            key=lambda item: item.get("timestamp") or "",
            reverse=True,
        )

        return {"items": history[:limit]}

    @router.get("/incidents/{incident_id}/replay")
    def replay_observed_incident(incident_id: UUID):
        events = recent_jsonl(EVENTS, limit=20000)

        related = [
            event
            for event in events
            if event.get("incident_id") == str(incident_id)
            and event.get("event") in REPLAY_EVENTS
            and parse_time(event.get("timestamp")) is not None
        ]

        if not related:
            raise HTTPException(
                status_code=404,
                detail="Incident not found in retained events",
            )

        related.sort(key=lambda event: event["timestamp"])

        created = next(
            (
                event for event in related
                if event["event"] == "INCIDENT_CREATED"
            ),
            related[0],
        )

        started_at = parse_time(created["timestamp"])

        resolved = next(
            (
                event for event in related
                if event["event"] == "INCIDENT_RESOLVED"
            ),
            None,
        )

        diagnosis = next(
            (
                event.get("fault_type")
                for event in related
                if event["event"] == "FAULT_DIAGNOSED"
            ),
            None,
        )

        route_change = next(
            (
                event for event in related
                if event["event"] == "ROUTE_CHANGE_SUCCESS"
            ),
            None,
        )

        timeline = []

        for event in related[:150]:
            phase, label = REPLAY_EVENTS[event["event"]]

            timeline.append({
                "event": event["event"],
                "phase": phase,
                "label": label,
                "timestamp": event["timestamp"],
                "elapsed_ms": elapsed_ms(
                    started_at,
                    parse_time(event["timestamp"]),
                ),
                "source": "controller_log",
                "association": "incident_id",
                "details": {
                    field: event[field]
                    for field in REPLAY_FIELDS
                    if field in event
                    and event[field] is not None
                },
            })

        return {
            "experiment_id": None,
            "incident_id": str(incident_id),
            "scenario": None,
            "fault_type": diagnosis,
            "status": "RESOLVED" if resolved else "OPEN",
            "verified_recovery": (
                resolved is not None
                and route_change is not None
            ),
            "replay_mode": "READ_ONLY",
            "timeline": timeline,
            "truncated": len(related) > 150,
            "metrics": {
                "first_failure_ms": None,
                "incident_created_ms": None,
                "incident_recovery_ms": elapsed_ms(
                    started_at,
                    parse_time(resolved["timestamp"])
                    if resolved else None,
                ),
                "total_recovery_ms": None,
                "route_change_ms": (
                    route_change.get("duration_ms")
                    if route_change else None
                ),
            },
        }

    return router