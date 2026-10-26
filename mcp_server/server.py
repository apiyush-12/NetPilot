from typing import Any, Literal

import httpx
from mcp.server import MCPServer
from mcp_server.guardrails import (sanitize_incidents, sanitize_events)

# Create our MCP server
mcp = MCPServer("NetPilot-MCP")

# Existing NetPilot backend
API_URL = "http://127.0.0.1:8000"

@mcp.tool()
def get_network_status() -> dict[str, Any]:
    """
    Read NetPilot network status.

    Returns connectivity, router, gateway,
    service and process information.

    READ-ONLY: Never modifies the network.
    """

    try:
        with httpx.Client(
            timeout=45.0,
            trust_env=False
        ) as client:
            response = client.get(
                f"{API_URL}/api/status"
            )
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            return {
                "ok": False,
                "error": "Invalid backend response"
            }

        return {
            "ok": True,
            "network": {
                "connected": data.get("connected"),
                "active_router": data.get("active_router"),
                "docker_online": data.get("docker_online"),
                "routes": data.get("routes"),
                "services": data.get("services"),
                "processes": data.get("processes"),
                "route_errors": data.get("route_errors"),
                "timestamp": data.get("timestamp")
            }
        }

    except (httpx.HTTPError, ValueError):
        return {
            "ok": False,
            "error": "Could not retrieve NetPilot status"
        }

@mcp.tool()
def get_incidents(limit: int = 10) -> dict[str, Any]:
    """
    Retrieve recent NetPilot network incidents.

    Returns incident IDs, fault types, statuses,
    timestamps, and recovery resolutions.

    READ-ONLY: Does not modify the network.
    """

    if not 1 <= limit <= 50:
        return {
            "ok": False,
            "error": "Limit must be between 1 and 50"
        }

    try:
        with httpx.Client(
            timeout=15.0,
            trust_env=False
        ) as client:
            response = client.get(
                f"{API_URL}/api/incidents",
                params={"limit": limit}
            )

            response.raise_for_status()
            data = response.json()

        items = sanitize_incidents(data.get("items"), limit)

        if not isinstance(items, list):
            return {
                "ok": False,
                "error": "Invalid incident response"
            }

        return {
            "ok": True,
            "count": len(items),
            "incidents": items
        }

    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return {
            "ok": False,
            "error": "Unable to retrieve incidents"
        }

@mcp.tool()
def get_incident_events(
    incident_id: str,
    limit: int = 100
) -> dict[str, Any]:
    """
    Retrieve detailed events for a specific NetPilot incident.

    Includes diagnosis, recovery attempts,
    route changes and resolution information.

    READ-ONLY: Never changes network configuration.
    """

    if not isinstance(incident_id, str) or not incident_id.strip():
        return {
            "ok": False,
            "error": "A valid incident ID is required"
        }

    if len(incident_id) > 128:
        return {
            "ok": False,
            "error": "Incident ID is too long"
        }

    if not 1 <= limit <= 200:
        return {
            "ok": False,
            "error": "Limit must be between 1 and 200"
        }

    try:
        with httpx.Client(
            timeout=15.0,
            trust_env=False
        ) as client:

            response = client.get(
                f"{API_URL}/api/events",
                params={
                    "incident_id": incident_id,
                    "limit": limit
                }
            )

            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Invalid response")

        events = sanitize_events(data.get("items"), incident_id, limit)

        if not isinstance(events, list):
            raise ValueError("Invalid events list")

        return {
            "ok": True,
            "incident_id": incident_id,
            "count": len(events),
            "events": events
        }

    except (httpx.HTTPError, ValueError):
        return {
            "ok": False,
            "error": "Unable to retrieve incident events"
        }

@mcp.tool()
def get_router_diagnostics(
    router: Literal["router-a", "router-b"]
) -> dict[str, Any]:
    """
    Retrieve real router diagnostics from NetPilot.

    Checks container status and IPv4 forwarding.

    READ-ONLY: Does not modify router configuration.
    """

    try:
        with httpx.Client(
            timeout=15.0,
            trust_env=False
        ) as client:

            response = client.get(
                f"{API_URL}/api/routers/{router}/diagnostics"
            )

            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            return {
                "ok": False,
                "error": "Invalid diagnostic response"
            }

        return {
            "ok": True,
            "diagnostics": data
        }

    except (httpx.HTTPError, ValueError):
        return {
            "ok": False,
            "error": "Unable to retrieve router diagnostics"
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")