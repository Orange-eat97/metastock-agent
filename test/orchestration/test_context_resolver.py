from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chat.models import ChatContext
from orchestration.context_resolver import (
    DecisionContextResolver,
)
from orchestration.decisions import (
    OrchestratorDecision,
    PlannerRequest,
    ToolManifestItem,
)


EXPLORER_ID = (
    "11111111-1111-4111-8111-111111111111"
)
RESULT_ID = (
    "22222222-2222-4222-8222-222222222222"
)


@dataclass
class ExactNameResolver:
    def resolve_explorer_id(
        self,
        explorer_name: str,
    ) -> str:
        assert explorer_name == "RSI Scanner"
        return EXPLORER_ID


def manifest_item(
    name: str,
    properties: dict[str, Any],
    *,
    enabled: bool = True,
) -> ToolManifestItem:
    return ToolManifestItem(
        name=name,
        description=name,
        enabled=enabled,
        input_schema={
            "type": "object",
            "properties": properties,
        },
    )


def request_for(
    tool: ToolManifestItem,
    *,
    context: ChatContext | None = None,
) -> PlannerRequest:
    return PlannerRequest(
        user_message="Test request",
        context=context or ChatContext(),
        tools=[tool],
        available_workflows=[
            "run_explorer"
        ],
    )


def test_resolves_exact_explorer_name() -> None:
    tool = manifest_item(
        "get_explorer",
        {"explorer_id": {"type": "string"}},
    )
    resolver = DecisionContextResolver(
        explorer_name_resolver=(
            ExactNameResolver()
        )
    )

    resolution = resolver.resolve(
        request=request_for(tool),
        decision=OrchestratorDecision(
            action="single_tool",
            tool_name="get_explorer",
            explorer_reference="RSI Scanner",
            decision_reason="Inspect it.",
        ),
    )

    assert resolution.outcome == "execute"
    assert resolution.arguments[
        "explorer_id"
    ] == EXPLORER_ID


def test_uses_active_explorer() -> None:
    tool = manifest_item(
        "get_explorer",
        {"explorer_id": {"type": "string"}},
    )
    resolver = DecisionContextResolver()

    resolution = resolver.resolve(
        request=request_for(
            tool,
            context=ChatContext(
                active_explorer_id=(
                    EXPLORER_ID
                )
            ),
        ),
        decision=OrchestratorDecision(
            action="single_tool",
            tool_name="get_explorer",
            explorer_reference="current",
            decision_reason="Inspect current.",
        ),
    )

    assert resolution.outcome == "execute"
    assert resolution.arguments[
        "explorer_id"
    ] == EXPLORER_ID


def test_missing_explorer_clarifies() -> None:
    tool = manifest_item(
        "get_explorer",
        {"explorer_id": {"type": "string"}},
    )

    resolution = (
        DecisionContextResolver()
        .resolve(
            request=request_for(tool),
            decision=OrchestratorDecision(
                action="single_tool",
                tool_name="get_explorer",
                decision_reason="Inspect.",
            ),
        )
    )

    assert resolution.outcome == "clarify"
    assert "active Explorer" in (
        resolution.message or ""
    )


def test_uses_active_result_id() -> None:
    tool = manifest_item(
        "get_explorer_result",
        {"result_id": {"type": "string"}},
    )

    resolution = (
        DecisionContextResolver()
        .resolve(
            request=request_for(
                tool,
                context=ChatContext(
                    active_result_id=RESULT_ID
                ),
            ),
            decision=OrchestratorDecision(
                action="single_tool",
                tool_name=(
                    "get_explorer_result"
                ),
                result_reference="current",
                decision_reason="Load result.",
            ),
        )
    )

    assert resolution.outcome == "execute"
    assert resolution.arguments[
        "result_id"
    ] == RESULT_ID


def test_filters_invented_arguments() -> None:
    tool = manifest_item(
        "generate_explorer",
        {"user_query": {"type": "string"}},
    )

    request = request_for(tool)
    request.user_message = "Generate RSI scan"

    resolution = (
        DecisionContextResolver()
        .resolve(
            request=request,
            decision=OrchestratorDecision(
                action="single_tool",
                tool_name=(
                    "generate_explorer"
                ),
                arguments={
                    "user_query": "truncated",
                    "raw_sql": "DROP TABLE",
                },
                decision_reason="Generate.",
            ),
        )
    )

    assert resolution.arguments == {
        "user_query": "Generate RSI scan"
    }


def test_disabled_tool_clarifies() -> None:
    tool = manifest_item(
        "revise_explorer",
        {
            "explorer_id": {
                "type": "string"
            },
            "revision_instruction": {
                "type": "string"
            },
        },
        enabled=False,
    )

    resolution = (
        DecisionContextResolver()
        .resolve(
            request=request_for(tool),
            decision=OrchestratorDecision(
                action="single_tool",
                tool_name="revise_explorer",
                decision_reason="Revise.",
            ),
        )
    )

    assert resolution.outcome == "clarify"
    assert "disabled" in (
        resolution.message or ""
    )
