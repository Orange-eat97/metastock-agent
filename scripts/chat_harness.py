from __future__ import annotations

import argparse
import os
from pathlib import Path
from uuid import UUID

from chat.controller import ChatTurnController
from chat.durable_cli import DurableChatCli
from infrastructure.agent_state import (
    AgentStateDatabase,
    AgentStateDatabaseSettings,
    ConversationRepository,
    LangChainHistoryFactory,
    TurnStreamRepository,
)
from infrastructure.agent_state.tool_call_repository import (
    ToolCallRepository,
)
from services import rag_client
from services.automator_client import (
    AutomatorClient,
    LocalAutomatorClient,
    UnavailableAutomatorClient,
)
from services.conversation_application_service import (
    ConversationApplicationService,
)
from services.explorer_repository import (
    ExplorerRepository,
)
from services.rag_client import LocalRagClient
from tools.explorer_tools import (
    ExplorerToolService,
)
from tools.tool_registry import ToolRegistry
from agent_workflows.explorer_review_workflow import (
    ExplorerReviewWorkflow,
)
from tools.result_tools import (
    MetaStockResultToolService,
)


def build_registry(
    rag_repo_path: str,
    automator_client: AutomatorClient,
) -> ToolRegistry:
    """
    Build the existing MetaStock business-tool registry.

    Conversation persistence is handled separately by
    ConversationApplicationService. This function only constructs
    the existing Explorer tool dependencies.
    """
    rag_client = LocalRagClient(
        rag_repo_path=rag_repo_path,
    )

    explorer_repository = ExplorerRepository(
        rag_client=rag_client,
    )

    workflow = ExplorerReviewWorkflow(
        rag_client=rag_client,
        explorer_repository=explorer_repository,
    )

    explorer_tools = ExplorerToolService(
        review_workflow=workflow,
        explorer_repository=explorer_repository,
        automator_client=automator_client,
    )

    result_tools = MetaStockResultToolService(
        automator_client=automator_client,
        result_client=rag_client,
    )

    return ToolRegistry(
        explorer_tool_service=explorer_tools,
        result_tool_service=result_tools,
    )

def build_automator_client(
    automator_repo_path: str | None,
) -> AutomatorClient:
    if not automator_repo_path:
        return UnavailableAutomatorClient()

    resolved_path = str(
        Path(automator_repo_path)
        .expanduser()
        .resolve()
    )

    return LocalAutomatorClient(resolved_path)


def build_conversation_service(
    *,
    database: AgentStateDatabase,
    registry: ToolRegistry,
) -> ConversationApplicationService:
    conversations = ConversationRepository(
        database.pool
    )

    history = LangChainHistoryFactory(
        database.pool
    )

    streams = TurnStreamRepository(
        database.pool
    )

    tool_calls = ToolCallRepository(
        database.pool
    )

    return ConversationApplicationService(
        conversations=conversations,
        history=history,
        streams=streams,
        tool_calls=tool_calls,
        registry=registry,
        controller_factory=(
            lambda recording_registry:
            ChatTurnController(
                recording_registry
            )
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "MetaStock durable conversation harness."
        )
    )

    parser.add_argument(
        "--rag-repo",
        default=os.getenv(
            "METASTOCK_RAG_REPO"
        ),
        help=(
            "Path to metastock-RAG-LLM. "
            "Defaults to METASTOCK_RAG_REPO."
        ),
    )

    parser.add_argument(
        "--automator-repo",
        default=os.getenv(
            "METASTOCK_AUTOMATOR_REPO"
        ),
        help=(
            "Path containing the MetaStock Automator "
            "service modules. Defaults to "
            "METASTOCK_AUTOMATOR_REPO."
        ),
    )

    selection = parser.add_mutually_exclusive_group()

    selection.add_argument(
        "--conversation-id",
        help=(
            "Resume an existing durable conversation."
        ),
    )

    selection.add_argument(
        "--new-conversation",
        action="store_true",
        help=(
            "Create and select a new conversation "
            "when the harness starts."
        ),
    )

    parser.add_argument(
        "--title",
        default=None,
        help=(
            "Optional title used with "
            "--new-conversation."
        ),
    )

    return parser.parse_args()


def parse_conversation_id(
    raw_value: str,
) -> UUID:
    try:
        return UUID(raw_value)
    except ValueError as exc:
        raise SystemExit(
            "Invalid --conversation-id value: "
            f"{raw_value}"
        ) from exc


def main() -> None:
    args = parse_args()

    if not args.rag_repo:
        raise SystemExit(
            "Provide --rag-repo or set "
            "METASTOCK_RAG_REPO."
        )

    if (
        args.title is not None
        and not args.new_conversation
    ):
        raise SystemExit(
            "--title can only be used with "
            "--new-conversation."
        )

    rag_repo_path = str(
        Path(args.rag_repo)
        .expanduser()
        .resolve()
    )

    automator_client = build_automator_client(
        args.automator_repo
    )

    registry = build_registry(
        rag_repo_path,
        automator_client,
    )

    settings = (
        AgentStateDatabaseSettings
        .from_environment()
    )

    with AgentStateDatabase(settings) as database:
        service = build_conversation_service(
            database=database,
            registry=registry,
        )

        active_conversation_id: UUID | None = None

        if args.conversation_id:
            requested_id = parse_conversation_id(
                args.conversation_id
            )

            conversation = (
                service.get_conversation(
                    requested_id
                )
            )

            active_conversation_id = (
                conversation.conversation_id
            )

        elif args.new_conversation:
            conversation = (
                service.create_conversation(
                    args.title
                )
            )

            active_conversation_id = (
                conversation.conversation_id
            )

            print(
                "Created conversation:",
                active_conversation_id,
            )

        print(
            "Automator configured:",
            automator_client.configured,
        )

        cli = DurableChatCli(
            service=service,
            active_conversation_id=(
                active_conversation_id
            ),
        )

        cli.run()


if __name__ == "__main__":
    main()