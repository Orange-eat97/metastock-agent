from __future__ import annotations

from langgraph.runtime import Runtime

from chat.models import (
    ChatContext,
    ChatTurnInput,
    ChatTurnOutput,
    PlannerConversationMessage,
)
from orchestration.action_policy import (
    ConversationActionPolicy,
)
from orchestration.context_resolver import (
    DecisionResolution,
)
from orchestration.conversation_actions import (
    ConversationModelRequest,
    ConversationModelResponse,
    build_conversation_actions,
)
from orchestration.conversation_model import (
    ConversationDriverProtocol,
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
)
from tools.tool_contracts import ToolResult


class InitializeConversationTurnNode:
    """Reset turn-local channels before a checkpointed thread's next turn."""

    def __call__(
        self,
        state: GraphInputState,
    ) -> MetaStockGraphState:
        _read_turn_input(state)

        return {
            "conversation_request": {},
            "conversation_response": {},
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


class ConverseNode:
    def __init__(
        self,
        *,
        driver: ConversationDriverProtocol,
        registry,
        workflows: StaticWorkflowCatalog,
    ) -> None:
        self._driver = driver
        self._registry = registry
        self._workflows = workflows

    def __call__(
        self,
        state: GraphInputState,
        runtime: Runtime[
            GraphRuntimeContext
        ],
    ) -> MetaStockGraphState:
        payload = _read_turn_input(state)

        request = ConversationModelRequest(
            user_message=payload.user_message,
            recent_messages=(
                _read_runtime_messages(runtime)
            ),
            context=payload.context,
            actions=build_conversation_actions(
                self._registry,
                self._workflows,
            ),
        )
        response = self._driver.converse(
            request
        )

        return {
            "conversation_request": (
                request.model_dump(
                    mode="json"
                )
            ),
            "conversation_response": (
                response.model_dump(
                    mode="json"
                )
            ),
        }


class ResolveConversationActionNode:
    def __init__(
        self,
        policy: ConversationActionPolicy,
    ) -> None:
        self._policy = policy

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        request = (
            ConversationModelRequest
            .model_validate(
                state.get(
                    "conversation_request"
                )
            )
        )
        response = (
            ConversationModelResponse
            .model_validate(
                state.get(
                    "conversation_response"
                )
            )
        )
        resolution = self._policy.resolve(
            request=request,
            response=response,
        )

        return {
            "resolution": (
                resolution.model_dump(
                    mode="json"
                )
            )
        }


class ComposeConversationResultNode:
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
            DecisionResolution
            .model_validate(
                state.get("resolution")
            )
        )
        conversation_response = (
            ConversationModelResponse
            .model_validate(
                state.get(
                    "conversation_response"
                )
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
            decision=None,
            action_name=(
                resolution.tool_name
                or resolution.workflow_name
            ),
            initial_assistant_message=(
                conversation_response
                .assistant_message
                or None
            ),
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


class FinalizeConversationTurnNode:
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
                or (
                    "I could not form a complete "
                    "response."
                )
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

    if (
        not isinstance(raw_result, dict)
        or not raw_result
    ):
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
        isinstance(
            raw_workflow_context,
            dict,
        )
        and raw_workflow_context
    ):
        return ChatContext.model_validate(
            raw_workflow_context
        )

    raw_context = state.get(
        "updated_context"
    )

    if (
        isinstance(raw_context, dict)
        and raw_context
    ):
        return ChatContext.model_validate(
            raw_context
        )

    return payload.context


def _deterministic_result_message(
    state: MetaStockGraphState,
    results: list[ToolResult],
) -> str:
    result = results[-1]
    rendered = _assistant_message(
        result
    )

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
        state.get(
            "workflow_failed_tool"
        )
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
