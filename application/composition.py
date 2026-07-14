from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from langgraph.checkpoint.base import BaseCheckpointSaver

from agent_workflows.explorer_review_workflow import ExplorerReviewWorkflow
from chat.controller import ChatTurnController
from infrastructure.agent_state import (
    AgentStateDatabase,
    CheckpointStoreProtocol,
    ConversationRepository,
    LangChainHistoryFactory,
    TurnStreamRepository,
)
from infrastructure.agent_state.tool_call_repository import ToolCallRepository
from orchestration.context_resolver import ExplorerReferenceResolverProtocol
from orchestration.orchestrator import LangGraphOrchestrator
from orchestration.planner import PlannerProtocol
from orchestration.response_composer import ResponseComposerProtocol
from services.automator_client import (
    AutomatorClient,
    LocalAutomatorClient,
    UnavailableAutomatorClient,
)
from services.conversation_application_service import (
    ChatControllerProtocol,
    ConversationApplicationService,
)
from services.explorer_name_resolver import ExplorerNameResolver
from services.explorer_repository import ExplorerRepository
from services.rag_client import LocalRagClient
from services.recording_tool_registry import ToolRegistryProtocol
from tools.explorer_tools import ExplorerToolService
from tools.result_tools import MetaStockResultToolService
from tools.tool_registry import ToolRegistry


ENV_ORCHESTRATOR = "AGENT_ORCHESTRATOR"


class OrchestratorMode(str, Enum):
    LEGACY = "legacy"
    LANGGRAPH = "langgraph"


ControllerFactory = Callable[
    [ToolRegistryProtocol],
    ChatControllerProtocol,
]


@dataclass(frozen=True, slots=True)
class BusinessDependencies:
    """Concrete business dependencies shared by both orchestrator modes."""

    rag_client: LocalRagClient
    automator_client: AutomatorClient
    registry: ToolRegistry
    explorer_name_resolver: ExplorerNameResolver


def resolve_orchestrator_mode(
    value: str | OrchestratorMode | None = None,
) -> OrchestratorMode:
    if isinstance(value, OrchestratorMode):
        return value

    raw_value = (
        value
        if value is not None
        else os.getenv(
            ENV_ORCHESTRATOR,
            OrchestratorMode.LANGGRAPH.value,
        )
    )
    cleaned = str(raw_value).strip().casefold()

    try:
        return OrchestratorMode(cleaned)
    except ValueError as exc:
        allowed = ", ".join(
            mode.value
            for mode in OrchestratorMode
        )
        raise ValueError(
            f"{ENV_ORCHESTRATOR} must be one of: {allowed}."
        ) from exc


def build_automator_client(
    automator_repo_path: str | None,
) -> AutomatorClient:
    if not automator_repo_path:
        return UnavailableAutomatorClient()

    return LocalAutomatorClient(
        automator_repo_path
    )


def build_business_dependencies(
    *,
    rag_repo_path: str,
    automator_client: AutomatorClient,
) -> BusinessDependencies:
    rag_client = LocalRagClient(
        rag_repo_path=rag_repo_path,
    )

    explorer_repository = ExplorerRepository(
        rag_client=rag_client,
    )

    review_workflow = ExplorerReviewWorkflow(
        rag_client=rag_client,
        explorer_repository=explorer_repository,
    )

    explorer_tools = ExplorerToolService(
        review_workflow=review_workflow,
        explorer_repository=explorer_repository,
        automator_client=automator_client,
    )

    result_tools = MetaStockResultToolService(
        automator_client=automator_client,
        result_client=rag_client,
    )

    registry = ToolRegistry(
        explorer_tool_service=explorer_tools,
        result_tool_service=result_tools,
    )

    return BusinessDependencies(
        rag_client=rag_client,
        automator_client=automator_client,
        registry=registry,
        explorer_name_resolver=ExplorerNameResolver(
            rag_client
        ),
    )


def build_controller_factory(
    *,
    mode: OrchestratorMode | str,
    planner: PlannerProtocol | None,
    response_composer: (
        ResponseComposerProtocol | None
    ),
    explorer_name_resolver: (
        ExplorerReferenceResolverProtocol | None
    ),
    checkpointer: BaseCheckpointSaver | None,
    enable_deterministic_fallback: bool = True,
) -> ControllerFactory:
    resolved_mode = resolve_orchestrator_mode(mode)

    if resolved_mode is OrchestratorMode.LEGACY:
        return (
            lambda recording_registry:
            ChatTurnController(
                recording_registry
            )
        )

    if planner is None:
        raise ValueError(
            "planner is required for the "
            "langgraph orchestrator."
        )

    if response_composer is None:
        raise ValueError(
            "response_composer is required for "
            "the langgraph orchestrator."
        )

    if explorer_name_resolver is None:
        raise ValueError(
            "explorer_name_resolver is required "
            "for the langgraph orchestrator."
        )

    if checkpointer is None:
        raise ValueError(
            "checkpointer is required for the "
            "production langgraph orchestrator."
        )

    return (
        lambda recording_registry:
        LangGraphOrchestrator(
            recording_registry,
            planner=planner,
            response_composer=(
                response_composer
            ),
            explorer_name_resolver=(
                explorer_name_resolver
            ),
            checkpointer=checkpointer,
            enable_deterministic_fallback=(
                enable_deterministic_fallback
            ),
        )
    )


def build_conversation_service(
    *,
    database: AgentStateDatabase,
    checkpoints: CheckpointStoreProtocol,
    registry: ToolRegistry,
    controller_factory: ControllerFactory,
) -> ConversationApplicationService:
    """Build the durable conversation service from explicit dependencies."""
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
        controller_factory=controller_factory,
        checkpoints=checkpoints,
    )
