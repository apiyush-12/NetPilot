import asyncio
import json

from mcp.client import Client
from mcp_server.server import mcp


async def main():
    async with Client(mcp) as client:

        # Discover the registered tools
        tools = await client.list_tools()

        print("Available MCP tools:")
        for tool in tools.tools:
            print("-", tool.name)

        # Call our first tool through MCP
        result = await client.call_tool(
            "get_network_status",
            {}
        )

        if result.is_error:
            print("MCP tool execution failed:")
            print(result)
            return

        print("\nNetwork Status:")
        print(
            json.dumps(
                result.structured_content,
                indent=2,
                default=str
            )
        )
        # Call the get_incidents tool
        incidents_result = await client.call_tool(
            "get_incidents",
            {"limit": 5}
        )

        if incidents_result.is_error:
            print("MCP tool execution failed:")
            print(incidents_result)
            return

        print("\nRecent Incidents:")
        print(
            json.dumps(
                incidents_result.structured_content,
                indent=2,
                default=str
            )
        )
        # Test detailed incident events
        incident_id = "93b86634-c330-406a-8adf-ec70dcb541ce"

        result = await client.call_tool(
            "get_incident_events",
            {
                "incident_id": incident_id,
                "limit": 100
            }
        )

        print("\nDetailed Incident Events:")
        print(
            json.dumps(
                result.structured_content,
                indent=2,
                default=str
            )
        )

        # Test router diagnostics for both routers
        for router in ["router-a", "router-b"]:

            result = await client.call_tool(
                "get_router_diagnostics",
                {"router": router}
            )

            print(f"\nDiagnostics for {router}:")

            print(
                json.dumps(
                    result.structured_content,
                    indent=2,
                    default=str
                )
            )

if __name__ == "__main__":
    asyncio.run(main())