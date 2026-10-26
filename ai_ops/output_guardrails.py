"""Deterministic screening of NetPilot AI responses."""

import os
import re

import httpx


class OutputGuardrailError(ValueError):
    """AI output must not be sent to the dashboard."""


ALLOWED_TOOLS = {
    "get_network_status",
    "get_incidents",
    "get_incident_events",
    "get_router_diagnostics",
}

API_URL = "http://127.0.0.1:8000"


async def screen_output(answer: str, tool_calls: list) -> dict:
    """
    Screen AI output and retrieve backend reference facts.

    This is basic verification, not a guarantee that every
    statement in an LLM response is correct.
    """

    if not isinstance(answer, str) or not answer.strip():
        raise OutputGuardrailError("Empty AI response.")

    if len(answer) > 20000:
        raise OutputGuardrailError("AI response exceeds size limit.")

    # Block accidental disclosure of known environment secrets.
    for name in (
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "NETPILOT_CONTROL_TOKEN",
    ):
        secret = os.getenv(name, "")

        if len(secret) >= 12 and secret in answer:
            raise OutputGuardrailError(
                "AI response contains sensitive information."
            )

    if re.search(r"\bgsk_[A-Za-z0-9_-]{16,}", answer):
        raise OutputGuardrailError(
            "Potential API credential detected in AI output."
        )

    tools = [
        call.get("tool")
        for call in tool_calls
        if isinstance(call, dict)
    ]

    if not set(tools).issubset(ALLOWED_TOOLS):
        raise OutputGuardrailError(
            "Unexpected tool recorded in investigation."
        )

    warnings = []
    reference_data = {}

    if not tools:
        warnings.append(
            "No MCP tool calls were recorded. "
            "The answer is not backed by live tool evidence."
        )

    # Fetch trusted reference facts separately from the model.
    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            trust_env=False
        ) as client:

            if "get_network_status" in tools:
                response = await client.get(
                    f"{API_URL}/api/status"
                )
                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict):
                    reference_data["network"] = {
                        "connected": data.get("connected"),
                        "active_router": data.get("active_router"),
                        "docker_online": data.get("docker_online"),
                    }

                    if not data.get("docker_online"):
                        warnings.append(
                            "Docker lab is unavailable; "
                            "live connectivity cannot be confirmed."
                        )

                    # Check a clearly labeled active-router claim.
                    for line in answer.splitlines():
                        normalized = (
                            line.strip()
                            .replace("*", "")
                            .replace("`", "")
                            .replace("‑", "-")
                        )

                        if not re.match(
                            r"^-?\s*active router\s*:",
                            normalized,
                            re.IGNORECASE,
                        ):
                            continue

                        match = re.search(
                            r"\brouter-[ab]\b",
                            normalized,
                            re.IGNORECASE,
                        )

                        actual = data.get("active_router")

                        if match and actual in (
                            "router-a", "router-b"
                        ):
                            if match.group().lower() != actual:
                                warnings.append(
                                    "The reported active router "
                                    "differs from the latest backend state."
                                )
                        break

            if "get_incidents" in tools:
                response = await client.get(
                    f"{API_URL}/api/incidents",
                    params={"limit": 1},
                )
                response.raise_for_status()

                items = response.json().get("items", [])

                if items and isinstance(items[0], dict):
                    incident = items[0]

                    reference_data["latest_incident"] = {
                        "incident_id": incident.get("incident_id"),
                        "status": incident.get("status"),
                        "fault_type": incident.get("fault_type"),
                        "resolution": incident.get("resolution"),
                    }

    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        warnings.append(
            "Backend evidence cross-check was unavailable."
        )

    return {
        "status": "warning" if warnings else "screened",
        "checks": {
            "output_format": "passed",
            "secret_scan": "passed",
            "tool_allowlist": "passed",
        },
        "warnings": warnings,
        "reference_data": reference_data,
    }