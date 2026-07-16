from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from PySide6.QtWidgets import QApplication

from application.composition import (
    OrchestratorMode,
    build_automator_client,
    build_business_dependencies,
    build_controller_factory,
    build_conversation_service,
)
from desktop_ui.adapters import Ms10ConversationAdapter
from desktop_ui.main_window import run
from infrastructure.agent_state import (
    AgentStateDatabase,
    AgentStateDatabaseSettings,
    CheckpointBackend,
    build_checkpoint_store,
)
from orchestration.conversation_model import OpenAIConversationDriver
from orchestration.response_composer import OpenAIResponseComposer
from services.conversation_export_service import ConversationLogExportService
from services.explorer_edit_service import ExplorerEditService
from services.explorer_repository import ExplorerRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the MS11 PySide6 desktop UI against the MS10 backend."
    )
    parser.add_argument(
        "--rag-repo",
        default=os.getenv("METASTOCK_RAG_REPO"),
        help="Path to the metastock-RAG-LLM repository.",
    )
    parser.add_argument(
        "--automator-repo",
        default=os.getenv("METASTOCK_AUTOMATOR_REPO"),
        help="Optional path to the metastock-automator repository.",
    )
    parser.add_argument(
        "--checkpoint-backend",
        default=os.getenv("AGENT_CHECKPOINT_BACKEND", "postgres"),
        choices=[backend.value for backend in CheckpointBackend],
    )
    parser.add_argument(
        "--conversation-model",
        default=(
            os.getenv("METASTOCK_CONVERSATION_MODEL")
            or os.getenv("METASTOCK_ORCHESTRATOR_MODEL")
        ),
    )
    parser.add_argument(
        "--response-model",
        default=os.getenv("METASTOCK_RESPONSE_MODEL"),
    )
    parser.add_argument(
        "--disable-deterministic-fallback",
        action="store_true",
    )
    return parser.parse_args()


def _resolve_required_repo(raw_path: str | None, label: str) -> str:
    if not raw_path:
        raise SystemExit(
            f"Provide --{label}-repo or set METASTOCK_{label.upper()}_REPO."
        )
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise SystemExit(f"{label.capitalize()} repository does not exist: {path}")
    return str(path)


def _resolve_optional_repo(raw_path: str | None) -> str | None:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise SystemExit(f"Automator repository does not exist: {path}")
    return str(path)


def main() -> int:
    args = parse_args()

    # Establish Qt's GUI/OLE apartment before the local Automator service is
    # constructed. This avoids the Windows RPC_E_CHANGED_MODE startup warning.
    application = QApplication.instance() or QApplication([sys.argv[0]])

    rag_repo = _resolve_required_repo(args.rag_repo, "rag")
    automator_repo = _resolve_optional_repo(args.automator_repo)

    automator_client = build_automator_client(automator_repo)
    dependencies = build_business_dependencies(
        rag_repo_path=rag_repo,
        automator_client=automator_client,
    )

    settings = AgentStateDatabaseSettings.from_environment()
    database = AgentStateDatabase(settings)
    checkpoint_backend = CheckpointBackend(args.checkpoint_backend)
    checkpoints = build_checkpoint_store(
        backend=checkpoint_backend,
        agent_state_settings=settings,
    )

    conversation_driver = OpenAIConversationDriver(
        model=args.conversation_model
    )
    response_composer = OpenAIResponseComposer(
        model=args.response_model or args.conversation_model
    )

    try:
        database.open()
        checkpoints.__enter__()

        controller_factory = build_controller_factory(
            mode=OrchestratorMode.LANGGRAPH,
            conversation_driver=conversation_driver,
            planner=None,
            response_composer=response_composer,
            explorer_name_resolver=dependencies.explorer_name_resolver,
            checkpointer=checkpoints.saver,
            enable_deterministic_fallback=(
                not args.disable_deterministic_fallback
            ),
        )
        service = build_conversation_service(
            database=database,
            checkpoints=checkpoints,
            registry=dependencies.registry,
            controller_factory=controller_factory,
        )
        explorer_edit_service = ExplorerEditService(
            ExplorerRepository(dependencies.rag_client)
        )
        conversation_export_service = ConversationLogExportService(
            service
        )
        return run(
            Ms10ConversationAdapter(
                service,
                explorer_edit_service=explorer_edit_service,
                conversation_export_service=conversation_export_service,
            ),
            application=application,
        )
    finally:
        checkpoints.close()
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
