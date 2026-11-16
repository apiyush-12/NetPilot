"""NetPilot read-only MCP server.

Reads the local Docker lab and controller event records directly.
Does not bypass or modify FastAPI authentication.
"""

from typing import Any, Literal

from mcp.server import MCPServer

from backend.core import (
    EVENTS,
    ControlError,
    Lab,
    incident_summary,
    recent_jsonl,
)

from mcp_server.guardrails import (
    sanitize_incidents,
    sanitize_events,
)


mcp = MCPServer("NetPilot-MCP")


@mcp.tool()
def get_network_status() -> dict[str, Any]:
    """
    Read NetPilot's current network status.

    READ-ONLY: Does not change Docker routes or services.
    """
    try:
        data = Lab().status({})

        return {
            "ok": True,
            "network": {
                "connected": data.get("connected"),
                "active_router": data.get("active_router"),
                "docker_online": data.get("docker_online"),
                "routes": data.get("routes"),
                "services": data.get("services"),
                "processes": None,
                "route_errors": data.get("route_errors"),
                "timestamp": data.get("timestamp"),
            },
        }

    except (ControlError, OSError, ValueError, TypeError):
        return {
            "ok": False,
            "error": "Could not retrieve NetPilot status",
        }


@mcp.tool()
def get_incidents(limit: int = 10) -> dict[str, Any]:
    """
    Retrieve recent incidents from local controller records.

    READ-ONLY: Does not modify incident history.
    """
    if not 1 <= limit <= 50:
        return {
            "ok": False,
            "error": "Limit must be between 1 and 50",
        }

    try:
        raw_items = incident_summary(limit)

        items = sanitize_incidents(
            raw_items,
            limit,
        )

        return {
            "ok": True,
            "count": len(items),
            "incidents": items,
        }

    except (OSError, ValueError, TypeError, AttributeError):
        return {
            "ok": False,
            "error": "Unable to retrieve incidents",
        }


@mcp.tool()
def get_incident_events(
    incident_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Retrieve recorded events for a specific incident.

    READ-ONLY: Does not modify event logs.
    """
    if not isinstance(incident_id, str) or not incident_id.strip():
        return {
            "ok": False,
            "error": "A valid incident ID is required",
        }

    if len(incident_id) > 128:
        return {
            "ok": False,
            "error": "Incident ID is too long",
        }

    if not 1 <= limit <= 200:
        return {
            "ok": False,
            "error": "Limit must be between 1 and 200",
        }

    try:
        raw_items = recent_jsonl(
            EVENTS,
            limit=limit,
            incident_id=incident_id,
        )

        events = sanitize_events(
            raw_items,
            incident_id,
            limit,
        )

        return {
            "ok": True,
            "incident_id": incident_id,
            "count": len(events),
            "events": events,
        }

    except (OSError, ValueError, TypeError, AttributeError):
        return {
            "ok": False,
            "error": "Unable to retrieve incident events",
        }


@mcp.tool()
def get_router_diagnostics(
    router: Literal["router-a", "router-b"],
) -> dict[str, Any]:
    """
    Read the selected router's Docker and IP forwarding status.

    READ-ONLY: Does not modify router configuration.
    """
    try:
        data = Lab().router_diagnostics(router)

        return {
            "ok": True,
            "diagnostics": data,
        }

    except (ControlError, OSError, ValueError, TypeError):
        return {
            "ok": False,
            "error": "Unable to retrieve router diagnostics",
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")