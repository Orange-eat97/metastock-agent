from __future__ import annotations

import os

os.environ.setdefault(
    "LANGGRAPH_STRICT_MSGPACK",
    "true",
)

import argparse
from pathlib import Path
from uuid import UUID

from application.composition import (
    OrchestratorMode,
    build_automator_client,
    build_business_dependencies,
    build_controller_factory,
    build_conversation_service,
    resolve_orchestrator_mode,
)
from chat.durable_cli import DurableChatCli
from infrastructure.agent_state import (
    AgentStateDatabase,
    AgentStateDatabaseSettings,
    CheckpointBackend,
    build_checkpoint_store,
)
from orchestration.planner import OpenAIPlanner
from orchestration.response_composer import (
    OpenAIResponseComposer,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MetaStock durable conversation harness."
    )

    parser.add_argument(
        "--rag-repo",
        default=os.getenv("METASTOCK_RAG_REPO"),
        help=(
            "Path to metastock-RAG-LLM. "
            "Defaults to METASTOCK_RAG_REPO."
        ),
    )
    parser.add_argument(
        "--automator-repo",
        default=os.getenv("METASTOCK_AUTOMATOR_REPO"),
        help=(
            "Path containing the MetaStock Automator service modules. "
            "Defaults to METASTOCK_AUTOMATOR_REPO."
        ),
    )
    parser.add_argument(
        "--orchestrator",
        choices=[mode.value for mode in OrchestratorMode],
        default=os.getenv(
            "AGENT_ORCHESTRATOR",
            OrchestratorMode.LANGGRAPH.value,
        ),
        help=(
            "Orchestrator implementation. Defaults to "
            "AGENT_ORCHESTRATOR or langgraph."
        ),
    )
    parser.add_argument(
        "--checkpoint-backend",
        choices=[
            backend.value
            for backend in CheckpointBackend
        ],
        default=os.getenv(
            "AGENT_CHECKPOINT_BACKEND",
            CheckpointBackend.POSTGRES.value,
        ),
        help=(
            "Checkpoint backend. Production defaults to postgres."
        ),
    )
    parser.add_argument(
        "--planner-model",
        default=os.getenv(
            "METASTOCK_ORCHESTRATOR_MODEL"
        ),
        help=(
            "Optional OpenAI planner model. Defaults to "
            "METASTOCK_ORCHESTRATOR_MODEL."
        ),
    )
    parser.add_argument(
        "--response-model",
        default=os.getenv(
            "METASTOCK_RESPONSE_MODEL"
        ),
        help=(
            "Optional OpenAI response-composer "
            "model. Defaults to "
            "METASTOCK_RESPONSE_MODEL, then "
            "the planner model."
        ),
    )

    parser.add_argument(
        "--disable-deterministic-fallback",
        action="store_true",
        help=(
            "Disable the temporary planner-error fallback to "
            "DeterministicChatRouter."
        ),
    )

    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--conversation-id",
        help="Resume an existing durable conversation.",
    )
    selection.add_argument(
        "--new-conversation",
        action="store_true",
        help=(
            "Create and select a new conversation when the "
            "harness starts."
        ),
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional title used with --new-conversation.",
    )

    return parser.parse_args()


def parse_conversation_id(raw_value: str) -> UUID:
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
            "Provide --rag-repo or set METASTOCK_RAG_REPO."
        )

    if args.title is not None and not args.new_conversation:
        raise SystemExit(
            "--title can only be used with --new-conversation."
        )

    rag_repo_path = str(
        Path(args.rag_repo).expanduser().resolve()
    )
    automator_repo_path = (
        str(Path(args.automator_repo).expanduser().resolve())
        if args.automator_repo
        else None
    )

    mode = resolve_orchestrator_mode(args.orchestrator)
    checkpoint_backend = CheckpointBackend(
        args.checkpoint_backend
    )

    automator_client = build_automator_client(
        automator_repo_path
    )
    dependencies = build_business_dependencies(
        rag_repo_path=rag_repo_path,
        automator_client=automator_client,
    )

    agent_state_settings = (
        AgentStateDatabaseSettings.from_environment()
    )
    database = AgentStateDatabase(
        agent_state_settings
    )
    checkpoints = build_checkpoint_store(
        backend=checkpoint_backend,
        agent_state_settings=agent_state_settings,
    )

    planner = (
        OpenAIPlanner(model=args.planner_model)
        if mode is OrchestratorMode.LANGGRAPH
        else None
    )
    response_composer = (
        OpenAIResponseComposer(
            model=(
                args.response_model
                or args.planner_model
            )
        )
        if mode is OrchestratorMode.LANGGRAPH
        else None
    )

    try:
        database.open()
        checkpoints.__enter__()

        controller_factory = build_controller_factory(
            mode=mode,
            planner=planner,
            response_composer=(
                response_composer
            ),
            explorer_name_resolver=(
                dependencies.explorer_name_resolver
            ),
            checkpointer=(
                checkpoints.saver
                if mode is OrchestratorMode.LANGGRAPH
                else None
            ),
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

        active_conversation_id: UUID | None = None

        if args.conversation_id:
            requested_id = parse_conversation_id(
                args.conversation_id
            )
            conversation = service.get_conversation(
                requested_id
            )
            active_conversation_id = (
                conversation.conversation_id
            )
        elif args.new_conversation:
            conversation = service.create_conversation(
                args.title
            )
            active_conversation_id = (
                conversation.conversation_id
            )
            print(
                "Created conversation:",
                active_conversation_id,
            )

        print("Orchestrator:", mode.value)
        print(
            "Checkpoint backend:",
            checkpoint_backend.value,
        )
        print(
            "Deterministic fallback:",
            (
                mode is OrchestratorMode.LANGGRAPH
                and not args.disable_deterministic_fallback
            ),
        )
        print(
            "Automator configured:",
            automator_client.configured,
        )

        cli = DurableChatCli(
            service=service,
            active_conversation_id=active_conversation_id,
        )
        cli.run()

    finally:
        checkpoints.close()
        database.close()


if __name__ == "__main__":
    main()
