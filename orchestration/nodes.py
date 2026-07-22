from __future__ import annotations

from langgraph.runtime import Runtime

from chat.controller import (
    ChatTurnController,
    ToolRegistryProtocol,
)
from chat.models import (
    ChatContext,
    ChatTurnInput,
    ChatTurnOutput,
    PlannerConversationMessage,
)
from chat.result_mapper import (
    update_context_from_tool_result,
)
from chat.router import (
    DeterministicChatRouter,
)
from orchestration.catalog import (
    ToolCatalogProtocol,
    build_tool_manifest,
)
from orchestration.context_resolver import (
    DecisionContextResolver,
    DecisionResolution,
)
from orchestration.decisions import (
    OrchestratorDecision,
    PlannerRequest,
)
from orchestration.planner import (
    PlannerProtocol,
)
from orchestration.registry_executor import (
    RegistryToolExecutor,
)
from orchestration.response_composer import (
    ResponseComposerProtocol,
    ResponseCompositionRequest,
    summarize_tool_result,
)
from orchestration.state import (
    GraphInputState,
    GraphRuntimeContext,
    MetaStockGraphState,
)
from orchestration.workflows import (
    StaticWorkflowCatalog,
    WorkflowPlan,
)
from tools.tool_contracts import (
    ToolResult,
    ToolStatus,
)


class InitializeTurnNode:
    """Clear turn-local channels before a persisted thread's next turn."""

    def __call__(
        self,
        state: GraphInputState,
    ) -> MetaStockGraphState:
        _read_turn_input(state)

        return {
            "planner_request": {},
            "decision": {},
            "resolution": {},
            "tool_result": {},
            "updated_context": {},
            "workflow_plan": {},
            "workflow_index": 0,
            "workflow_results": [],
            "workflow_context": {},
            "workflow_complete": False,
            "workflow_succeeded": False,
            "workflow_failed_tool": None,
            "composed_response": "",
            "turn_output": {},
        }


class DeterministicTurnNode:
    def __init__(
        self,
        *,
        registry: ToolRegistryProtocol,
        router: (
            DeterministicChatRouter | None
        ) = None,
    ) -> None:
        self._controller = ChatTurnController(
            registry=registry,
            router=router,
        )

    def __call__(
        self,
        state: GraphInputState,
    ) -> MetaStockGraphState:
        payload = _read_turn_input(state)
        output = self._controller.handle_turn(
            payload
        )

        return {
            "turn_output": output.model_dump(
                mode="json"
            )
        }


class PlanTurnNode:
    def __init__(
        self,
        *,
        planner: PlannerProtocol,
        registry: ToolCatalogProtocol,
        available_workflows: list[str],
    ) -> None:
        self._planner = planner
        self._registry = registry
        self._available_workflows = list(
            available_workflows
        )

    def __call__(
        self,
        state: GraphInputState,
        runtime: Runtime[
            GraphRuntimeContext
        ],
    ) -> MetaStockGraphState:
        payload = _read_turn_input(state)

        request = PlannerRequest(
            user_message=(
                payload.user_message
            ),
            recent_messages=(
                _read_runtime_messages(runtime)
            ),
            context=payload.context,
            tools=build_tool_manifest(
                self._registry
            ),
            available_workflows=(
                self._available_workflows
            ),
        )

        decision = self._planner.plan(
            request
        )

        return {
            "planner_request": (
                request.model_dump(
                    mode="json"
                )
            ),
            "decision": (
                decision.model_dump(
                    mode="json"
                )
            ),
        }


class ResolveDecisionNode:
    def __init__(
        self,
        resolver: DecisionContextResolver,
    ) -> None:
        self._resolver = resolver

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        request = PlannerRequest.model_validate(
            state.get("planner_request")
        )
        decision = (
            OrchestratorDecision
            .model_validate(
                state.get("decision")
            )
        )

        resolution = self._resolver.resolve(
            request=request,
            decision=decision,
        )

        return {
            "resolution": (
                resolution.model_dump(
                    mode="json"
                )
            )
        }


class ExecuteResolvedToolNode:
    def __init__(
        self,
        executor: RegistryToolExecutor,
    ) -> None:
        self._executor = executor

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        payload = _read_turn_input(state)
        resolution = (
            DecisionResolution
            .model_validate(
                state.get("resolution")
            )
        )

        if (
            resolution.outcome != "execute"
            or not resolution.tool_name
        ):
            raise RuntimeError(
                "ExecuteResolvedToolNode "
                "received a non-executable "
                "resolution."
            )

        result = self._executor.execute(
            resolution.tool_name,
            resolution.arguments,
        )

        updated_context = (
            update_context_from_tool_result(
                payload.context,
                result,
            )
        )

        return {
            "tool_result": result.model_dump(
                mode="json"
            ),
            "updated_context": (
                updated_context.model_dump(
                    mode="json"
                )
            ),
        }


class PrepareWorkflowNode:
    def __init__(
        self,
        catalog: StaticWorkflowCatalog,
    ) -> None:
        self._catalog = catalog

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        payload = _read_turn_input(state)
        resolution = (
            DecisionResolution
            .model_validate(
                state.get("resolution")
            )
        )

        if (
            resolution.outcome != "workflow"
            or not resolution.workflow_name
        ):
            raise RuntimeError(
                "PrepareWorkflowNode received "
                "a non-workflow resolution."
            )

        explorer_id = str(
            resolution.arguments.get(
                "explorer_id"
            )
            or ""
        ).strip()

        if not explorer_id:
            raise RuntimeError(
                "The resolved workflow has no "
                "explorer_id."
            )

        plan = self._catalog.prepare(
            workflow_name=(
                resolution.workflow_name
            ),
            explorer_id=explorer_id,
        )

        return {
            "workflow_plan": (
                plan.model_dump(
                    mode="json"
                )
            ),
            "workflow_index": 0,
            "workflow_results": [],
            "workflow_context": (
                payload.context.model_dump(
                    mode="json"
                )
            ),
            "workflow_complete": False,
            "workflow_succeeded": False,
            "workflow_failed_tool": None,
        }


class ExecuteWorkflowStepNode:
    def __init__(
        self,
        executor: RegistryToolExecutor,
    ) -> None:
        self._executor = executor

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        plan = WorkflowPlan.model_validate(
            state.get("workflow_plan")
        )
        index = int(
            state.get("workflow_index", 0)
        )

        if index < 0 or index >= len(
            plan.steps
        ):
            raise RuntimeError(
                "Workflow step index is out "
                "of bounds."
            )

        context = ChatContext.model_validate(
            state.get("workflow_context")
            or {}
        )
        previous_results = list(
            state.get("workflow_results")
            or []
        )

        step = plan.steps[index]
        arguments = {
            "explorer_id": plan.explorer_id,
            **step.argument_overrides,
        }

        result = self._executor.execute(
            step.tool_name,
            arguments,
        )
        next_context = (
            update_context_from_tool_result(
                context,
                result,
            )
        )

        next_results = [
            *previous_results,
            result.model_dump(
                mode="json"
            ),
        ]
        next_index = index + 1

        step_succeeded = (
            result.ok
            and result.status
            is ToolStatus.SUCCESS
        )
        workflow_complete = (
            not step_succeeded
            or next_index >= len(plan.steps)
        )

        return {
            "workflow_index": next_index,
            "workflow_results": next_results,
            "workflow_context": (
                next_context.model_dump(
                    mode="json"
                )
            ),
            "workflow_complete": (
                workflow_complete
            ),
            "workflow_succeeded": (
                step_succeeded
                and next_index
                >= len(plan.steps)
            ),
            "workflow_failed_tool": (
                None
                if step_succeeded
                else step.tool_name
            ),
        }


class ComposeAssistantResponseNode:
    def __init__(
        self,
        composer: ResponseComposerProtocol,
    ) -> None:
        self._composer = composer

    def __call__(
        self,
        state: MetaStockGraphState,
        runtime: Runtime[
            GraphRuntimeContext
        ],
    ) -> MetaStockGraphState:
        payload = _read_turn_input(state)
        resolution = (
            DecisionResolution.model_validate(
                state.get("resolution")
            )
        )
        decision = (
            OrchestratorDecision.model_validate(
                state.get("decision")
            )
        )

        results = _read_tool_results(state)
        context = _read_final_context(
            state,
            payload,
        )
        fallback_message = (
            _deterministic_result_message(
                state,
                results,
            )
        )

        request = ResponseCompositionRequest(
            user_message=payload.user_message,
            recent_messages=(
                _read_runtime_messages(runtime)
            ),
            decision=decision,
            route=resolution.route.value,
            context=context,
            workflow_name=(
                resolution.workflow_name
            ),
            workflow_succeeded=(
                bool(
                    state.get(
                        "workflow_succeeded"
                    )
                )
                if state.get("workflow_plan")
                else None
            ),
            failed_tool=state.get(
                "workflow_failed_tool"
            ),
            tool_results=[
                summarize_tool_result(result)
                for result in results
            ],
            fallback_message=fallback_message,
        )

        return {
            "composed_response": (
                self._composer.compose(
                    request
                ).strip()
                or fallback_message
            )
        }


class FinalizeTurnNode:
    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        payload = _read_turn_input(state)
        resolution = (
            DecisionResolution
            .model_validate(
                state.get("resolution")
            )
        )
        results = _read_tool_results(state)

        if results:
            result = results[-1]
            context = _read_final_context(
                state,
                payload,
            )
            message = (
                str(
                    state.get(
                        "composed_response"
                    )
                    or ""
                ).strip()
                or _deterministic_result_message(
                    state,
                    results,
                )
            )
        else:
            result = None
            context = payload.context
            message = (
                resolution.message
                or "No tool was executed."
            )

        output = ChatTurnOutput(
            assistant_message=message,
            route=resolution.route,
            context=context,
            tool_result=result,
        )

        return {
            "turn_output": output.model_dump(
                mode="json"
            )
        }


def route_after_resolution(
    state: MetaStockGraphState,
) -> str:
    resolution = (
        DecisionResolution.model_validate(
            state.get("resolution")
        )
    )

    if resolution.outcome == "execute":
        return "execute"

    if resolution.outcome == "workflow":
        return "workflow"

    if resolution.outcome == "sequence":
        return "sequence"

    return "finalize"


def route_after_workflow_step(
    state: MetaStockGraphState,
) -> str:
    return (
        "compose"
        if bool(
            state.get(
                "workflow_complete",
                False,
            )
        )
        else "continue"
    )


def _read_turn_input(
    state: GraphInputState,
) -> ChatTurnInput:
    raw_input = state.get("turn_input")

    if not isinstance(raw_input, dict):
        raise ValueError(
            "Graph state must contain a "
            "dictionary at 'turn_input'."
        )

    return ChatTurnInput.model_validate(
        raw_input
    )


def _read_runtime_messages(
    runtime: Runtime[
        GraphRuntimeContext
    ],
) -> list[PlannerConversationMessage]:
    raw_messages = (
        runtime.context.get(
            "recent_messages",
            [],
        )
        if runtime.context
        else []
    )

    return [
        PlannerConversationMessage
        .model_validate(message)
        for message in raw_messages
    ]


def _read_tool_results(
    state: MetaStockGraphState,
) -> list[ToolResult]:
    workflow_results = list(
        state.get("workflow_results")
        or []
    )

    if workflow_results:
        return [
            ToolResult.model_validate(result)
            for result in workflow_results
        ]

    raw_result = state.get("tool_result")

    if not isinstance(raw_result, dict) or not raw_result:
        return []

    return [
        ToolResult.model_validate(
            raw_result
        )
    ]


def _read_final_context(
    state: MetaStockGraphState,
    payload: ChatTurnInput,
) -> ChatContext:
    raw_workflow_context = state.get(
        "workflow_context"
    )

    if (
        isinstance(raw_workflow_context, dict)
        and raw_workflow_context
    ):
        return ChatContext.model_validate(
            raw_workflow_context
        )

    raw_context = state.get(
        "updated_context"
    )

    if isinstance(raw_context, dict) and raw_context:
        return ChatContext.model_validate(
            raw_context
        )

    return payload.context


def _deterministic_result_message(
    state: MetaStockGraphState,
    results: list[ToolResult],
) -> str:
    result = results[-1]
    rendered = _assistant_message(result)

    if not state.get("workflow_plan"):
        return rendered

    if bool(
        state.get(
            "workflow_succeeded",
            False,
        )
    ):
        return rendered

    tool_label = (
        state.get("workflow_failed_tool")
        or result.tool_name
    )

    return (
        f"Workflow stopped at "
        f"`{tool_label}`.\n\n"
        f"{rendered}"
    )


def _assistant_message(
    result: ToolResult,
) -> str:
    if (
        result.display
        and result.display.markdown.strip()
    ):
        return result.display.markdown

    return result.message
