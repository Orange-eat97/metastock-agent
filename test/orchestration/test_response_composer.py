from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from chat.models import ChatContext
from orchestration.decisions import (
    OrchestratorDecision,
)
from orchestration.response_composer import (
    ComposedAssistantResponse,
    OpenAIResponseComposer,
    ResponseComposerWithFallback,
    ResponseCompositionRequest,
    summarize_tool_result,
)
from tools.tool_contracts import (
    ToolResult,
    ToolStatus,
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
                ComposedAssistantResponse(
                    assistant_message=(
                        "The Explorer was generated."
                    )
                )
            )
        )


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


class ExplodingComposer:
    def compose(self, request) -> str:
        del request
        raise RuntimeError("composer down")


class FallbackComposer:
    def compose(self, request) -> str:
        return request.fallback_message


def request() -> ResponseCompositionRequest:
    return ResponseCompositionRequest(
        user_message="Generate RSI scan",
        decision=OrchestratorDecision(
            action="single_tool",
            tool_name="generate_explorer",
            decision_reason="Generate.",
        ),
        route="generate_explorer",
        context=ChatContext(),
        fallback_message="Generated.",
    )


def test_openai_composer_uses_structured_parse() -> None:
    client = FakeClient()
    composer = OpenAIResponseComposer(
        model="test-model",
        client=client,
    )

    message = composer.compose(request())

    assert message == (
        "The Explorer was generated."
    )
    assert client.responses.arguments[
        "model"
    ] == "test-model"
    assert client.responses.arguments[
        "text_format"
    ] is ComposedAssistantResponse


def test_composer_failure_returns_grounded_fallback() -> None:
    composer = ResponseComposerWithFallback(
        primary=ExplodingComposer(),
        fallback=FallbackComposer(),
    )

    assert composer.compose(request()) == (
        "Generated."
    )


def test_tool_summary_omits_large_rows() -> None:
    summary = summarize_tool_result(
        ToolResult(
            tool_name="read_results",
            ok=True,
            status=ToolStatus.SUCCESS,
            message="Read results.",
            data={
                "rows": [
                    {"symbol": str(index)}
                    for index in range(50)
                ],
                "result_id": "result-1",
            },
        )
    )

    assert summary.data["rows"] == {
        "omitted": True,
        "item_count": 50,
    }
    assert summary.data[
        "result_id"
    ] == "result-1"
