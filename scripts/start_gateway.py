"""Start the existing MetaStock agent behind MCP stdio or a local HTTP frontend.

Usage (from repository root):
  python -m scripts.start_gateway --transport stdio
  python -m scripts.start_gateway --transport http
Environment follows scripts/chat_harness.py plus METASTOCK_GATEWAY_TOKEN for HTTP.
"""
from __future__ import annotations

import os
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

import argparse
import asyncio
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from application.composition import (
    OrchestratorMode, build_automator_client, build_business_dependencies,
    build_controller_factory, build_conversation_service,
)
from infrastructure.agent_state import (
    AgentStateDatabase, AgentStateDatabaseSettings,
    CheckpointBackend, build_checkpoint_store,
)
from orchestration.conversation_model import OpenAIConversationDriver
from orchestration.response_composer import OpenAIResponseComposer
from mcp_adapters.agent_gateway import AgentGateway


@contextmanager
def build_gateway() -> Iterator[AgentGateway]:
    rag_repo = os.getenv("METASTOCK_RAG_REPO")
    if not rag_repo:
        raise ValueError("METASTOCK_RAG_REPO is required")
    automator_repo = os.getenv("METASTOCK_AUTOMATOR_REPO")
    dependencies = build_business_dependencies(
        rag_repo_path=str(Path(rag_repo).expanduser().resolve()),
        automator_client=build_automator_client(
            str(Path(automator_repo).expanduser().resolve()) if automator_repo else None
        ),
    )
    settings = AgentStateDatabaseSettings.from_environment()
    database = AgentStateDatabase(settings)
    checkpoints = build_checkpoint_store(
        backend=CheckpointBackend(os.getenv("AGENT_CHECKPOINT_BACKEND", "postgres")),
        agent_state_settings=settings,
    )
    try:
        database.open()
        checkpoints.__enter__()
        model = os.getenv("METASTOCK_CONVERSATION_MODEL") or os.getenv("METASTOCK_ORCHESTRATOR_MODEL")
        controller_factory = build_controller_factory(
            mode=OrchestratorMode.LANGGRAPH,
            conversation_driver=OpenAIConversationDriver(model=model),
            response_composer=OpenAIResponseComposer(
                model=os.getenv("METASTOCK_RESPONSE_MODEL") or model
            ),
            explorer_name_resolver=dependencies.explorer_name_resolver,
            checkpointer=checkpoints.saver,
        )
        service = build_conversation_service(
            database=database, checkpoints=checkpoints,
            registry=dependencies.registry, controller_factory=controller_factory,
        )
        yield AgentGateway(service)
    finally:
        checkpoints.close()
        database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8734)
    args = parser.parse_args()
    with build_gateway() as gateway:
        if args.transport == "stdio":
            from mcp_adapters.agent_mcp import serve
            asyncio.run(serve(gateway))
        else:
            from mcp_adapters.agent_http import serve_http
            serve_http(gateway, token=os.getenv("METASTOCK_GATEWAY_TOKEN", ""), port=args.port)


if __name__ == "__main__":
    main()
