"""Start MetaStock ToolRegistry over MCP, with a separate JSONL invocation audit."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from application.composition import build_automator_client, build_business_dependencies
from mcp_adapters.tool_bridge import McpInvocationAudit, PublicToolBridge
from mcp_adapters.tool_server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="MetaStock host-routed MCP tool server")
    parser.add_argument("--audit", default=os.getenv("METASTOCK_MCP_AUDIT", "logs/mcp_calls.jsonl"))
    args = parser.parse_args()
    rag_repo = os.getenv("METASTOCK_RAG_REPO")
    if not rag_repo:
        raise SystemExit("METASTOCK_RAG_REPO is required")
    automator_repo = os.getenv("METASTOCK_AUTOMATOR_REPO")
    dependencies = build_business_dependencies(
        rag_repo_path=str(Path(rag_repo).expanduser().resolve()),
        automator_client=build_automator_client(
            str(Path(automator_repo).expanduser().resolve()) if automator_repo else None
        ),
    )
    bridge = PublicToolBridge(dependencies.registry, McpInvocationAudit(args.audit))
    asyncio.run(serve(bridge))


if __name__ == "__main__":
    main()
