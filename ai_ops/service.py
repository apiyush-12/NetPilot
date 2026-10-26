import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents import Agent, Runner, set_tracing_disabled
from agents.mcp import MCPServerStdio, create_static_tool_filter

from ai_ops.agent_cli import (
    ALLOWED_TOOLS,
    INSTRUCTIONS,
    ToolAuditHooks,
    selected_model,
)

from ai_ops.guardrails import (
    InputGuardrailError,
    validate_question,
)

from ai_ops.output_guardrails import (
    OutputGuardrailError,
    screen_output,
)

from ai_ops.audit import record_audit


ROOT = Path(__file__).resolve().parent.parent


async def analyze_question(question: str) -> dict[str, Any]:
    """Run a guarded, read-only AI investigation."""

    audit_id = str(uuid4())

    # G1: Input validation.
    try:
        question = validate_question(question)

    except InputGuardrailError:
        record_audit(
            audit_id,
            "input",
            "blocked",
            "INPUT_POLICY",
        )
        raise

    record_audit(
        audit_id,
        "input",
        "passed",
        "INPUT_ACCEPTED",
    )

    set_tracing_disabled(True)

    hooks = ToolAuditHooks()

    try:
        provider, model_name, model = selected_model()

        async with MCPServerStdio(
            name="NetPilot Read-Only MCP",
            params={
                "command": sys.executable,
                "args": ["-m", "mcp_server.server"],
                "cwd": str(ROOT),
            },
            tool_filter=create_static_tool_filter(
                allowed_tool_names=ALLOWED_TOOLS
            ),
            use_structured_content=True,
            client_session_timeout_seconds=45,
        ) as server:

            agent = Agent(
                name="NetPilot Network Analyst",
                instructions=INSTRUCTIONS,
                model=model,
                mcp_servers=[server],
            )

            result = await Runner.run(
                agent,
                question,
                max_turns=12,
                hooks=hooks,
            )

        answer = str(result.final_output)

        # G3: Output screening and evidence cross-check.
        guardrail_result = await screen_output(
            answer,
            hooks.calls,
        )

    except OutputGuardrailError:
        record_audit(
            audit_id,
            "output",
            "blocked",
            "OUTPUT_POLICY",
            hooks.calls,
        )
        raise

    except Exception:
        record_audit(
            audit_id,
            "investigation",
            "failed",
            "EXECUTION_ERROR",
            hooks.calls,
        )
        raise

    # G4: Record output screening result.
    record_audit(
        audit_id,
        "output",
        guardrail_result["status"],
        "OUTPUT_SCREENED",
        hooks.calls,
    )

    return {
        "audit_id": audit_id,
        "provider": provider,
        "model": model_name,
        "question": question,
        "answer": answer,
        "tool_calls": hooks.calls,
        "guardrails": guardrail_result,
    }