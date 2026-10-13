"""MCP chat surface; the host may still own its dialogue engine.

Use the HTTP adapter if genuine passive-frontend behavior is required.
Requires the official `mcp` Python SDK v2.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
import mcp.server.stdio
import mcp.types as types

from mcp_adapters.agent_gateway import AgentGateway


def build_server(gateway: AgentGateway) -> Server:
    schemas: dict[str, tuple[str, dict[str, Any]]] = {
        "agent_create_conversation": (
            "Create a conversation in the MetaStock agent backend.",
            {"type": "object", "properties": {"title": {"type": "string"}}, "additionalProperties": False},
        ),
        "agent_chat": (
            "Submit one user turn to the MetaStock agent, which owns reasoning and tools.",
            {"type": "object", "properties": {
                "conversation_id": {"type": "string", "format": "uuid"},
                "message": {"type": "string", "minLength": 1},
                "client_turn_id": {"type": "string", "format": "uuid"},
            }, "required": ["conversation_id", "message"], "additionalProperties": False},
        ),
        "agent_get_history": (
            "Retrieve conversation turns persisted by MetaStock agent.",
            {"type": "object", "properties": {"conversation_id": {"type": "string", "format": "uuid"}},
             "required": ["conversation_id"], "additionalProperties": False},
        ),
    }

    async def list_tools(_ctx: Any, _params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[
            types.Tool(name=n, description=d, inputSchema=s)
            for n, (d, s) in schemas.items()
        ])

    async def call_tool(_ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        args = params.arguments or {}
        try:
            if params.name == "agent_create_conversation":
                result = gateway.create_conversation(args.get("title"))
            elif params.name == "agent_chat":
                result = gateway.chat(args["conversation_id"], args["message"], args.get("client_turn_id"))
            elif params.name == "agent_get_history":
                result = gateway.get_history(args["conversation_id"])
            else:
                raise ValueError("Unknown MCP tool")
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
                structuredContent=result,
            )
        except (KeyError, TypeError, ValueError, LookupError) as exc:
            msg = f"{type(exc).__name__}: {exc}"
            return types.CallToolResult(content=[types.TextContent(type="text", text=msg)], isError=True)
        except Exception as exc:
            # Server-side tracebacks must not leak database secrets or environment details.
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Agent call failed: {type(exc).__name__}")],
                isError=True,
            )

    return Server("metastock-agent", on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(gateway: AgentGateway) -> None:
    server = build_server(gateway)
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
