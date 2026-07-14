from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
)
from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from chat.controller import (
    ToolRegistryProtocol,
)
from chat.router import (
    DeterministicChatRouter,
)
from orchestration.action_policy import (
    ConversationActionPolicy,
)
from orchestration.context_resolver import (
    ExplorerReferenceResolverProtocol,
)
from orchestration.conversation_model import (
    ConversationDriverProtocol,
    ConversationDriverWithFallback,
    DeterministicConversationDriver,
)
from orchestration.conversation_nodes import (
    ComposeConversationResultNode,
    ConverseNode,
    FinalizeConversationTurnNode,
    InitializeConversationTurnNode,
    ResolveConversationActionNode,
)
from orchestration.conversation_workflow_nodes import (
    ExecuteConversationWorkflowStepNode,
    PrepareConversationWorkflowNode,
)
from orchestration.nodes import (
    ExecuteResolvedToolNode,
    route_after_resolution,
    route_after_workflow_step,
)
from orchestration.registry_executor import (
    RegistryToolExecutor,
)
from orchestration.response_composer import (
    DeterministicResponseComposer,
    ResponseComposerProtocol,
    ResponseComposerWithFallback,
)
from orchestration.state import (
    GraphInputState,
    GraphOutputState,
    GraphRuntimeContext,
    MetaStockGraphState,
)
from orchestration.workflows import (
    StaticWorkflowCatalog,
)


INITIALIZE_NODE = (
    "initialize_conversation_turn"
)
CONVERSE_NODE = "converse"
RESOLVE_ACTION_NODE = "resolve_action"
EXECUTE_NODE = "execute_tool"
PREPARE_WORKFLOW_NODE = "prepare_workflow"
EXECUTE_WORKFLOW_STEP_NODE = (
    "execute_workflow_step"
)
COMPOSE_RESULT_NODE = (
    "compose_conversation_result"
)
FINALIZE_NODE = "finalize_conversation_turn"


def build_conversational_graph(
    *,
    registry: ToolRegistryProtocol,
    driver: ConversationDriverProtocol,
    response_composer: (
        ResponseComposerProtocol | None
    ) = None,
    explorer_name_resolver: (
        ExplorerReferenceResolverProtocol
        | None
    ) = None,
    fallback_router: (
        DeterministicChatRouter | None
    ) = None,
    enable_deterministic_fallback: bool = True,
    checkpointer: (
        BaseCheckpointSaver | None
    ) = None,
) -> Any:
    workflow_catalog = (
        StaticWorkflowCatalog()
    )

    effective_driver = driver

    if enable_deterministic_fallback:
        effective_driver = (
            ConversationDriverWithFallback(
                primary=driver,
                fallback=(
                    DeterministicConversationDriver(
                        fallback_router
                    )
                ),
            )
        )

    deterministic_composer = (
        DeterministicResponseComposer()
    )
    effective_composer = (
        deterministic_composer
    )

    if response_composer is not None:
        effective_composer = (
            ResponseComposerWithFallback(
                primary=response_composer,
                fallback=(
                    deterministic_composer
                ),
            )
        )

    executor = RegistryToolExecutor(
        registry
    )
    policy = ConversationActionPolicy(
        registry=registry,
        explorer_name_resolver=(
            explorer_name_resolver
        ),
    )

    builder = StateGraph(
        MetaStockGraphState,
        context_schema=GraphRuntimeContext,
        input_schema=GraphInputState,
        output_schema=GraphOutputState,
    )

    builder.add_node(
        INITIALIZE_NODE,
        InitializeConversationTurnNode(),
    )
    builder.add_node(
        CONVERSE_NODE,
        ConverseNode(
            driver=effective_driver,
            registry=registry,
            workflows=workflow_catalog,
        ),
    )
    builder.add_node(
        RESOLVE_ACTION_NODE,
        ResolveConversationActionNode(
            policy
        ),
    )
    builder.add_node(
        EXECUTE_NODE,
        ExecuteResolvedToolNode(
            executor
        ),
    )
    builder.add_node(
        PREPARE_WORKFLOW_NODE,
        PrepareConversationWorkflowNode(
            workflow_catalog
        ),
    )
    builder.add_node(
        EXECUTE_WORKFLOW_STEP_NODE,
        ExecuteConversationWorkflowStepNode(
            executor
        ),
    )
    builder.add_node(
        COMPOSE_RESULT_NODE,
        ComposeConversationResultNode(
            effective_composer
        ),
    )
    builder.add_node(
        FINALIZE_NODE,
        FinalizeConversationTurnNode(),
    )

    builder.add_edge(
        START,
        INITIALIZE_NODE,
    )
    builder.add_edge(
        INITIALIZE_NODE,
        CONVERSE_NODE,
    )
    builder.add_edge(
        CONVERSE_NODE,
        RESOLVE_ACTION_NODE,
    )

    builder.add_conditional_edges(
        RESOLVE_ACTION_NODE,
        route_after_resolution,
        {
            "execute": EXECUTE_NODE,
            "workflow": (
                PREPARE_WORKFLOW_NODE
            ),
            "finalize": FINALIZE_NODE,
        },
    )

    builder.add_edge(
        EXECUTE_NODE,
        COMPOSE_RESULT_NODE,
    )
    builder.add_edge(
        PREPARE_WORKFLOW_NODE,
        EXECUTE_WORKFLOW_STEP_NODE,
    )

    builder.add_conditional_edges(
        EXECUTE_WORKFLOW_STEP_NODE,
        route_after_workflow_step,
        {
            "continue": (
                EXECUTE_WORKFLOW_STEP_NODE
            ),
            "compose": (
                COMPOSE_RESULT_NODE
            ),
        },
    )

    builder.add_edge(
        COMPOSE_RESULT_NODE,
        FINALIZE_NODE,
    )
    builder.add_edge(
        FINALIZE_NODE,
        END,
    )

    return builder.compile(
        checkpointer=checkpointer
    )
