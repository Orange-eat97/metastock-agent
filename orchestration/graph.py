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

from chat.controller import ToolRegistryProtocol
from chat.router import (
    DeterministicChatRouter,
)
from orchestration.context_resolver import (
    DecisionContextResolver,
    ExplorerReferenceResolverProtocol,
)
from orchestration.nodes import (
    ComposeAssistantResponseNode,
    DeterministicTurnNode,
    ExecuteResolvedToolNode,
    ExecuteWorkflowStepNode,
    FinalizeTurnNode,
    InitializeTurnNode,
    PlanTurnNode,
    PrepareWorkflowNode,
    ResolveDecisionNode,
    route_after_resolution,
    route_after_workflow_step,
)
from orchestration.planner import (
    DeterministicFallbackPlanner,
    PlannerProtocol,
    PlannerWithFallback,
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


INITIALIZE_NODE = "initialize_turn"
DETERMINISTIC_TURN_NODE = (
    "execute_deterministic_turn"
)
PLAN_NODE = "plan_turn"
RESOLVE_NODE = "resolve_decision"
EXECUTE_NODE = "execute_tool"
PREPARE_WORKFLOW_NODE = "prepare_workflow"
EXECUTE_WORKFLOW_STEP_NODE = (
    "execute_workflow_step"
)
COMPOSE_RESPONSE_NODE = (
    "compose_assistant_response"
)
FINALIZE_NODE = "finalize_turn"


def build_deterministic_parity_graph(
    *,
    registry: ToolRegistryProtocol,
    router: (
        DeterministicChatRouter | None
    ) = None,
    checkpointer: (
        BaseCheckpointSaver | None
    ) = None,
) -> Any:
    builder = StateGraph(
        MetaStockGraphState,
        context_schema=GraphRuntimeContext,
        input_schema=GraphInputState,
        output_schema=GraphOutputState,
    )

    builder.add_node(
        INITIALIZE_NODE,
        InitializeTurnNode(),
    )
    builder.add_node(
        DETERMINISTIC_TURN_NODE,
        DeterministicTurnNode(
            registry=registry,
            router=router,
        ),
    )

    builder.add_edge(
        START,
        INITIALIZE_NODE,
    )
    builder.add_edge(
        INITIALIZE_NODE,
        DETERMINISTIC_TURN_NODE,
    )
    builder.add_edge(
        DETERMINISTIC_TURN_NODE,
        END,
    )

    return builder.compile(
        checkpointer=checkpointer
    )


def build_structured_planning_graph(
    *,
    registry: ToolRegistryProtocol,
    planner: PlannerProtocol,
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
    available_workflows: (
        list[str] | None
    ) = None,
    enable_deterministic_fallback: bool = True,
    checkpointer: (
        BaseCheckpointSaver | None
    ) = None,
) -> Any:
    workflow_catalog = StaticWorkflowCatalog()

    resolved_workflows = (
        list(available_workflows)
        if available_workflows is not None
        else workflow_catalog.list_workflows()
    )

    unknown_workflows = (
        set(resolved_workflows)
        - set(
            workflow_catalog
            .list_workflows()
        )
    )

    if unknown_workflows:
        raise ValueError(
            "Unknown configured workflows: "
            + ", ".join(
                sorted(unknown_workflows)
            )
        )

    effective_planner: PlannerProtocol = planner

    if enable_deterministic_fallback:
        effective_planner = PlannerWithFallback(
            primary=planner,
            fallback=(
                DeterministicFallbackPlanner(
                    fallback_router
                )
            ),
        )

    deterministic_composer = (
        DeterministicResponseComposer()
    )
    effective_composer: ResponseComposerProtocol = (
        deterministic_composer
    )

    if response_composer is not None:
        effective_composer = (
            ResponseComposerWithFallback(
                primary=response_composer,
                fallback=deterministic_composer,
            )
        )

    executor = RegistryToolExecutor(
        registry
    )

    builder = StateGraph(
        MetaStockGraphState,
        context_schema=GraphRuntimeContext,
        input_schema=GraphInputState,
        output_schema=GraphOutputState,
    )

    builder.add_node(
        INITIALIZE_NODE,
        InitializeTurnNode(),
    )
    builder.add_node(
        PLAN_NODE,
        PlanTurnNode(
            planner=effective_planner,
            registry=registry,
            available_workflows=(
                resolved_workflows
            ),
        ),
    )
    builder.add_node(
        RESOLVE_NODE,
        ResolveDecisionNode(
            DecisionContextResolver(
                explorer_name_resolver=(
                    explorer_name_resolver
                )
            )
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
        PrepareWorkflowNode(
            workflow_catalog
        ),
    )
    builder.add_node(
        EXECUTE_WORKFLOW_STEP_NODE,
        ExecuteWorkflowStepNode(
            executor
        ),
    )
    builder.add_node(
        COMPOSE_RESPONSE_NODE,
        ComposeAssistantResponseNode(
            effective_composer
        ),
    )
    builder.add_node(
        FINALIZE_NODE,
        FinalizeTurnNode(),
    )

    builder.add_edge(
        START,
        INITIALIZE_NODE,
    )
    builder.add_edge(
        INITIALIZE_NODE,
        PLAN_NODE,
    )
    builder.add_edge(
        PLAN_NODE,
        RESOLVE_NODE,
    )

    builder.add_conditional_edges(
        RESOLVE_NODE,
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
        COMPOSE_RESPONSE_NODE,
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
                COMPOSE_RESPONSE_NODE
            ),
        },
    )

    builder.add_edge(
        COMPOSE_RESPONSE_NODE,
        FINALIZE_NODE,
    )
    builder.add_edge(
        FINALIZE_NODE,
        END,
    )

    return builder.compile(
        checkpointer=checkpointer
    )
