from __future__ import annotations

from typing import Any

from chat.models import (
    ChatTurnInput,
    PlannerConversationMessage,
)
from orchestration.decisions import (
    OrchestratorDecision,
    PlannerRequest,
)
from orchestration.orchestrator import (
    LangGraphOrchestrator,
)


class EmptyRegistry:
    def list_tools(self) -> list[Any]:
        return []

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ):
        raise AssertionError(
            f"Unexpected tool call: {name} "
            f"{arguments}"
        )


class CapturingPlanner:
    def __init__(self) -> None:
        self.request: PlannerRequest | None = None

    def plan(
        self,
        request: PlannerRequest,
    ) -> OrchestratorDecision:
        self.request = request
        return OrchestratorDecision(
            action="respond",
            response_message=(
                "The earlier threshold was 30."
            ),
            decision_reason=(
                "Answer from recent conversation."
            ),
        )


class SpyGraph:
    def __init__(self) -> None:
        self.input = None
        self.context = None

    def invoke(
        self,
        input,
        config=None,
        *,
        context=None,
    ):
        del config
        self.input = input
        self.context = context
        return {
            "turn_output": {
                "assistant_message": "ok",
                "route": "respond",
                "context": {},
                "tool_result": None,
            }
        }


def test_recent_messages_reach_planner_via_runtime_context() -> None:
    planner = CapturingPlanner()
    orchestrator = LangGraphOrchestrator(
        EmptyRegistry(),
        planner=planner,
    )

    output = orchestrator.handle_turn(
        ChatTurnInput(
            user_message=(
                "Why did you use 30?"
            ),
            recent_messages=[
                PlannerConversationMessage(
                    role="user",
                    content=(
                        "Generate RSI below 30"
                    ),
                ),
                PlannerConversationMessage(
                    role="assistant",
                    content=(
                        "I generated the scan."
                    ),
                ),
            ],
        )
    )

    assert output.assistant_message == (
        "The earlier threshold was 30."
    )
    assert planner.request is not None
    assert [
        message.content
        for message
        in planner.request.recent_messages
    ] == [
        "Generate RSI below 30",
        "I generated the scan.",
    ]


def test_recent_messages_are_not_put_in_graph_state() -> None:
    graph = SpyGraph()
    orchestrator = LangGraphOrchestrator(
        EmptyRegistry(),
        graph=graph,
    )

    orchestrator.handle_turn(
        ChatTurnInput(
            user_message="Follow up",
            recent_messages=[
                PlannerConversationMessage(
                    role="user",
                    content="private prior turn",
                )
            ],
        )
    )

    assert "recent_messages" not in (
        graph.input["turn_input"]
    )
    assert graph.context == {
        "recent_messages": [
            {
                "role": "user",
                "content": "private prior turn",
            }
        ]
    }
