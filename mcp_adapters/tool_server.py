"""Low-level MCP stdio server that publishes existing public tool JSON schemas."""
from __future__ import annotations

import json
from typing import Any

from mcp.server import Server
import mcp.server.stdio
import mcp.types as types

from mcp_adapters.tool_bridge import PublicToolBridge


def build_server(bridge: PublicToolBridge) -> Server:
    async def list_tools(_ctx: Any, _params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[
            types.Tool(
                name=definition.name,
                description=definition.description,
                inputSchema=definition.input_json_schema(),
            )
            for definition in bridge.definitions()
        ])

    async def call_tool(_ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            payload = bridge.invoke(params.name, params.arguments or {})
        except (ValueError, TypeError, KeyError) as exc:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Invalid tool call: {type(exc).__name__}")],
                isError=True,
            )
        except Exception as exc:
            # Backend exceptions may contain secrets. Do not return message/traceback.
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Tool execution failed: {type(exc).__name__}")],
                isError=True,
            )
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
            structuredContent=payload,
            isError=not payload["ok"],
        )

    return Server("metastock-tools", on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(bridge: PublicToolBridge) -> None:
    server = build_server(bridge)
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
