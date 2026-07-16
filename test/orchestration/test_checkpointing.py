from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import (
    InMemorySaver,
)
from pydantic import BaseModel

from chat.models import (
    ChatContext,
    ChatTurnInput,
)
from chat.routes import ChatRoute
from orchestration.decisions import (
    OrchestratorDecision,
    PlannerRequest,
)
from orchestration.orchestrator import (
    LangGraphOrchestrator,
)
from tools.tool_contracts import (
    GenerateExplorerInput,
    ToolResult,
    ToolStatus,
)


EXPLORER_ID = (
    "11111111-1111-4111-8111-111111111111"
)


@dataclass
class Definition:
    name: str
    input_model: type[BaseModel]
    enabled: bool = True
    description: str = "test"

    def input_json_schema(
        self,
    ) -> dict[str, Any]:
        return (
            self.input_model
            .model_json_schema()
        )


class Registry:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []
        self._tools = [
            Definition(
                "generate_explorer",
                GenerateExplorerInput,
            )
        ]

    def list_tools(
        self,
    ) -> list[Definition]:
        return list(self._tools)

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        self.calls.append(
            (name, dict(arguments))
        )

        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message="generated",
            data={
                "explorer": {
                    "explorer_id": (
                        EXPLORER_ID
                    )
                }
            },
        )


class SequencePlanner:
    def __init__(
        self,
        *decisions: OrchestratorDecision,
    ) -> None:
        self._decisions = list(decisions)

    def plan(
        self,
        request: PlannerRequest,
    ) -> OrchestratorDecision:
        del request

        if not self._decisions:
            raise AssertionError(
                "No planner decision remains."
            )

        return self._decisions.pop(0)


def config_for(
    thread_id: UUID,
) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": str(thread_id),
        }
    }


def test_checkpointed_orchestrator_requires_thread_id() -> None:
    orchestrator = LangGraphOrchestrator(
        Registry(),
        planner=SequencePlanner(
            OrchestratorDecision(
                action="respond",
                response_message="Hello",
                decision_reason="Respond.",
            )
        ),
        checkpointer=InMemorySaver(),
    )

    with pytest.raises(
        ValueError,
        match="thread_id",
    ):
        orchestrator.handle_turn(
            ChatTurnInput(
                user_message="Hello"
            )
        )


def test_completed_turn_creates_checkpoints() -> None:
    saver = InMemorySaver()
    thread_id = uuid4()

    orchestrator = LangGraphOrchestrator(
        Registry(),
        planner=SequencePlanner(
            OrchestratorDecision(
                action="single_tool",
                tool_name=(
                    "generate_explorer"
                ),
                decision_reason="Generate.",
            )
        ),
        checkpointer=saver,
    )

    output = orchestrator.handle_turn(
        ChatTurnInput(
            user_message="Generate RSI scan",
            thread_id=thread_id,
        )
    )

    checkpoints = list(
        saver.list(
            config_for(thread_id)
        )
    )

    assert checkpoints
    assert output.route is (
        ChatRoute.GENERATE_EXPLORER
    )


def test_threads_are_isolated() -> None:
    saver = InMemorySaver()
    first = uuid4()
    second = uuid4()

    orchestrator = LangGraphOrchestrator(
        Registry(),
        planner=SequencePlanner(
            OrchestratorDecision(
                action="respond",
                response_message="First",
                decision_reason="Respond.",
            ),
            OrchestratorDecision(
                action="respond",
                response_message="Second",
                decision_reason="Respond.",
            ),
        ),
        checkpointer=saver,
    )

    for thread_id, message in (
        (first, "first"),
        (second, "second"),
    ):
        orchestrator.handle_turn(
            ChatTurnInput(
                user_message=message,
                thread_id=thread_id,
            )
        )

    assert list(
        saver.list(config_for(first))
    )
    assert list(
        saver.list(config_for(second))
    )


def test_new_turn_does_not_reuse_stale_output() -> None:
    saver = InMemorySaver()
    thread_id = uuid4()

    orchestrator = LangGraphOrchestrator(
        Registry(),
        planner=SequencePlanner(
            OrchestratorDecision(
                action="respond",
                response_message=(
                    "First response"
                ),
                decision_reason="Respond.",
            ),
            OrchestratorDecision(
                action="clarify",
                response_message=(
                    "Which Explorer?"
                ),
                decision_reason="Clarify.",
            ),
        ),
        checkpointer=saver,
    )

    first = orchestrator.handle_turn(
        ChatTurnInput(
            user_message="Hello",
            thread_id=thread_id,
        )
    )
    second = orchestrator.handle_turn(
        ChatTurnInput(
            user_message="Open it",
            context=ChatContext(),
            thread_id=thread_id,
        )
    )

    assert first.assistant_message == (
        "First response"
    )
    assert second.assistant_message == (
        "Which Explorer?"
    )
    assert second.route is ChatRoute.CLARIFY
