import sys
from pathlib import Path
from typing import Any

from agents import Agent, Runner, set_tracing_disabled
from agents.mcp import (
    MCPServerStdio,
    create_static_tool_filter,
)

from ai_ops.agent_cli import (
    ALLOWED_TOOLS,
    INSTRUCTIONS,
    ToolAuditHooks,
    selected_model,
)

ROOT = Path(__file__).resolve().parent.parent


async def analyze_question(question: str) -> dict[str, Any]:
    """Run a read-only NetPilot AI investigation."""

    set_tracing_disabled(True)

    try:
        provider, model_name, model = selected_model()
    except SystemExit as error:
        raise RuntimeError(
            "NetPilot AI provider is not configured correctly"
        ) from error

    hooks = ToolAuditHooks()

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

    return {
        "provider": provider,
        "model": model_name,
        "question": question,
        "answer": str(result.final_output),
        "tool_calls": hooks.calls,
    }