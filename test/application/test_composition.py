from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import (
    InMemorySaver,
)

from application.composition import (
    OrchestratorMode,
    build_controller_factory,
    resolve_orchestrator_mode,
)
from chat.controller import ChatTurnController
from orchestration.decisions import (
    OrchestratorDecision,
    PlannerRequest,
)
from orchestration.orchestrator import (
    LangGraphOrchestrator,
)
from orchestration.response_composer import (
    DeterministicResponseComposer,
)
from tools.tool_contracts import (
    ToolResult,
    ToolStatus,
)


class FakeRegistry:
    def list_tools(self) -> list[Any]:
        return []

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message="passed",
            data={
                "arguments": arguments
            },
        )


class StaticPlanner:
    def plan(
        self,
        request: PlannerRequest,
    ) -> OrchestratorDecision:
        del request

        return OrchestratorDecision(
            action="respond",
            response_message="Hello",
            decision_reason="Respond.",
        )


class FakeResolver:
    def resolve_explorer_id(
        self,
        explorer_name: str,
    ) -> str:
        del explorer_name

        return (
            "11111111-1111-4111-8111-"
            "111111111111"
        )


def test_default_mode_is_langgraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "AGENT_ORCHESTRATOR",
        raising=False,
    )

    assert resolve_orchestrator_mode() is (
        OrchestratorMode.LANGGRAPH
    )


def test_environment_can_select_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENT_ORCHESTRATOR",
        "legacy",
    )

    assert resolve_orchestrator_mode() is (
        OrchestratorMode.LEGACY
    )


def test_invalid_mode_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="AGENT_ORCHESTRATOR",
    ):
        resolve_orchestrator_mode(
            "invented"
        )


def test_legacy_factory_retains_rollback() -> None:
    factory = build_controller_factory(
        mode=OrchestratorMode.LEGACY,
        planner=None,
        response_composer=None,
        explorer_name_resolver=None,
        checkpointer=None,
    )

    controller = factory(
        FakeRegistry()
    )

    assert isinstance(
        controller,
        ChatTurnController,
    )


def test_langgraph_factory_is_conversational_and_checkpointed() -> None:
    factory = build_controller_factory(
        mode=OrchestratorMode.LANGGRAPH,
        planner=StaticPlanner(),
        response_composer=(
            DeterministicResponseComposer()
        ),
        explorer_name_resolver=(
            FakeResolver()
        ),
        checkpointer=InMemorySaver(),
    )

    controller = factory(
        FakeRegistry()
    )

    assert isinstance(
        controller,
        LangGraphOrchestrator,
    )
    assert controller.structured_mode is True
    assert (
        controller.checkpointing_enabled
        is True
    )


@pytest.mark.parametrize(
    (
        "planner",
        "composer",
        "resolver",
        "checkpointer",
        "expected_message",
    ),
    [
        (
            None,
            DeterministicResponseComposer(),
            FakeResolver(),
            InMemorySaver(),
            "planner",
        ),
        (
            StaticPlanner(),
            None,
            FakeResolver(),
            InMemorySaver(),
            "response_composer",
        ),
        (
            StaticPlanner(),
            DeterministicResponseComposer(),
            None,
            InMemorySaver(),
            "explorer_name_resolver",
        ),
        (
            StaticPlanner(),
            DeterministicResponseComposer(),
            FakeResolver(),
            None,
            "checkpointer",
        ),
    ],
)
def test_langgraph_factory_requires_all_dependencies(
    planner,
    composer,
    resolver,
    checkpointer,
    expected_message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=expected_message,
    ):
        build_controller_factory(
            mode=(
                OrchestratorMode.LANGGRAPH
            ),
            planner=planner,
            response_composer=composer,
            explorer_name_resolver=resolver,
            checkpointer=checkpointer,
        )
