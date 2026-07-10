from __future__ import annotations

import argparse
import os
from pathlib import Path

from chat.controller import ChatTurnController
from chat.models import ChatContext, ChatTurnInput
from services.explorer_repository import ExplorerRepository
from services.rag_client import LocalRagClient
from tools.explorer_tools import ExplorerToolService
from tools.tool_registry import ToolRegistry
from workflows.explorer_review_workflow import ExplorerReviewWorkflow


def build_registry(rag_repo_path: str) -> ToolRegistry:
    rag_client = LocalRagClient(rag_repo_path=rag_repo_path)
    repository = ExplorerRepository(rag_client=rag_client)

    workflow = ExplorerReviewWorkflow(
        rag_client=rag_client,
        explorer_repository=repository,
    )
    explorer_tools = ExplorerToolService(
        review_workflow=workflow,
        explorer_repository=repository,
    )
    return ToolRegistry(explorer_tool_service=explorer_tools)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Milestone 3 deterministic MetaStock chat harness."
    )
    parser.add_argument(
        "--rag-repo",
        default=os.getenv("METASTOCK_RAG_REPO"),
        help=(
            "Path to metastock-RAG-LLM. Defaults to METASTOCK_RAG_REPO."
        ),
    )
    parser.add_argument(
        "--explorer-id",
        default=None,
        help="Optional Explorer ID to seed the transient session context.",
    )
    parser.add_argument(
        "--service-log-id",
        default=None,
        help="Optional RAG service log ID to seed the transient session context.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.rag_repo:
        raise SystemExit(
            "Provide --rag-repo or set METASTOCK_RAG_REPO, for example:\n"
            "  set METASTOCK_RAG_REPO=C:\\GitHub\\metastock-RAG-LLM"
        )

    rag_repo_path = str(Path(args.rag_repo).expanduser().resolve())
    registry = build_registry(rag_repo_path)
    controller = ChatTurnController(registry)

    context = ChatContext(
        active_explorer_id=args.explorer_id,
        active_service_log_id=args.service_log_id,
    )

    print("MetaStock Milestone 3 chat harness")
    print("Type /state to inspect transient IDs or /quit to exit.")

    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return

        if not message:
            continue

        if message.lower() in {"/quit", "/exit"}:
            return

        if message.lower() == "/state":
            print(context.model_dump_json(indent=2))
            continue

        output = controller.handle_turn(
            ChatTurnInput(
                user_message=message,
                context=context,
            )
        )
        context = output.context

        print(f"\nRoute: {output.route.value}")
        print(f"Assistant:\n{output.assistant_message}")

        if output.tool_result is not None:
            print(
                "\nTool status: "
                f"{output.tool_result.status.value}; ok={output.tool_result.ok}"
            )


if __name__ == "__main__":
    main()
