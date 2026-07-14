from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from chat.models import ChatContext
from orchestration.decisions import (
    OrchestratorDecision,
    PlannerRequest,
    ToolManifestItem,
)
from orchestration.planner import (
    OpenAIPlanner,
)


class FakeResponses:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}

    def parse(
        self,
        **kwargs: Any,
    ) -> Any:
        self.arguments = kwargs

        return SimpleNamespace(
            output_parsed=(
                OrchestratorDecision(
                    action="single_tool",
                    tool_name=(
                        "generate_explorer"
                    ),
                    decision_reason=(
                        "Generate a new scan."
                    ),
                )
            )
        )


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_openai_planner_uses_structured_parse() -> None:
    client = FakeClient()
    planner = OpenAIPlanner(
        model="test-model",
        client=client,
    )

    decision = planner.plan(
        PlannerRequest(
            user_message="Generate RSI scan",
            context=ChatContext(),
            tools=[
                ToolManifestItem(
                    name="generate_explorer",
                    description="Generate.",
                    input_schema={
                        "type": "object",
                        "properties": {},
                    },
                )
            ],
        )
    )

    assert decision.tool_name == (
        "generate_explorer"
    )
    assert client.responses.arguments[
        "model"
    ] == "test-model"
    assert client.responses.arguments[
        "text_format"
    ] is OrchestratorDecision
