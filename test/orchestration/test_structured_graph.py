from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    GetExplorerInput,
    ToolDisplay,
    ToolResult,
    ToolStatus,
)


EXPLORER_ID = (
    "11111111-1111-4111-8111-111111111111"
)
RESULT_ID = (
    "22222222-2222-4222-8222-222222222222"
)


@dataclass
class FakeToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    enabled: bool = True

    def input_json_schema(
        self,
    ) -> dict[str, Any]:
        return (
            self.input_model
            .model_json_schema()
        )


class MinimalInput(BaseModel):
    explorer_id: str
    instruments: str = "all"


class ReadInput(BaseModel):
    explorer_id: str
    close_after_read: bool = True


class FakeRegistry:
    def __init__(
        self,
        *,
        fail_on: str | None = None,
        blocked_on: str | None = None,
    ) -> None:
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []
        self.fail_on = fail_on
        self.blocked_on = blocked_on

        self._tools = [
            FakeToolDefinition(
                name="generate_explorer",
                description="Generate.",
                input_model=(
                    GenerateExplorerInput
                ),
            ),
            FakeToolDefinition(
                name="get_explorer",
                description="Get.",
                input_model=GetExplorerInput,
            ),
            *[
                FakeToolDefinition(
                    name=name,
                    description=name,
                    input_model=MinimalInput,
                )
                for name in (
                    "create_explorer_in_metastock",
                    "select_explorer_in_metastock",
                    "run_selected_explorer_in_metastock",
                )
            ],
            FakeToolDefinition(
                name=(
                    "read_metastock_explorer_results"
                ),
                description="Read.",
                input_model=ReadInput,
            ),
        ]

    def list_tools(
        self,
    ) -> list[FakeToolDefinition]:
        return list(self._tools)

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        self.calls.append(
            (name, dict(arguments))
        )

        if name == self.fail_on:
            return ToolResult(
                tool_name=name,
                ok=False,
                status=ToolStatus.FAILED,
                message="failed",
            )

        if name == self.blocked_on:
            return ToolResult(
                tool_name=name,
                ok=False,
                status=ToolStatus.BLOCKED,
                message="blocked",
            )

        data: dict[str, Any] = {}

        if name == "generate_explorer":
            data = {
                "explorer": {
                    "explorer_id": (
                        EXPLORER_ID
                    ),
                }
            }
        elif name == "get_explorer":
            data = {
                "explorer": {
                    "explorer_id": (
                        arguments[
                            "explorer_id"
                        ]
                    )
                }
            }
        elif name == (
            "read_metastock_explorer_results"
        ):
            data = {
                "explorer_id": EXPLORER_ID,
                "result_id": RESULT_ID,
            }

        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message=f"{name} passed",
            data=data,
            display=ToolDisplay(
                title="Passed",
                markdown=f"{name} markdown",
                severity="success",
            ),
        )


class StaticPlanner:
    def __init__(
        self,
        decision: OrchestratorDecision,
    ) -> None:
        self.decision = decision
        self.requests: list[
            PlannerRequest
        ] = []

    def plan(
        self,
        request: PlannerRequest,
    ) -> OrchestratorDecision:
        self.requests.append(request)
        return self.decision


def make_orchestrator(
    *,
    registry: FakeRegistry,
    workflow_name: str,
) -> LangGraphOrchestrator:
    return LangGraphOrchestrator(
        registry,
        planner=StaticPlanner(
            OrchestratorDecision(
                action="workflow",
                workflow_name=workflow_name,
                explorer_reference="current",
                decision_reason="Workflow.",
            )
        ),
    )


def test_single_tool_still_executes() -> None:
    registry = FakeRegistry()
    planner = StaticPlanner(
        OrchestratorDecision(
            action="single_tool",
            tool_name="generate_explorer",
            decision_reason="Generate.",
        )
    )

    output = LangGraphOrchestrator(
        registry,
        planner=planner,
    ).handle_turn(
        ChatTurnInput(
            user_message="Generate RSI scan"
        )
    )

    assert registry.calls == [
        (
            "generate_explorer",
            {
                "user_query": (
                    "Generate RSI scan"
                )
            },
        )
    ]
    assert output.route is (
        ChatRoute.GENERATE_EXPLORER
    )


def test_run_workflow_executes_in_order() -> None:
    registry = FakeRegistry()

    output = make_orchestrator(
        registry=registry,
        workflow_name="run_explorer",
    ).handle_turn(
        ChatTurnInput(
            user_message="Run this Explorer.",
            context=ChatContext(
                active_explorer_id=(
                    EXPLORER_ID
                )
            ),
        )
    )

    assert [
        name
        for name, _ in registry.calls
    ] == [
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
    ]
    assert output.route is (
        ChatRoute.RUN_EXPLORER
    )
    assert output.tool_result is not None
    assert output.tool_result.ok is True


def test_run_and_capture_executes_in_order() -> None:
    registry = FakeRegistry()

    output = make_orchestrator(
        registry=registry,
        workflow_name="run_and_capture",
    ).handle_turn(
        ChatTurnInput(
            user_message=(
                "Run this Explorer and capture "
                "the results."
            ),
            context=ChatContext(
                active_explorer_id=(
                    EXPLORER_ID
                )
            ),
        )
    )

    assert [
        name
        for name, _ in registry.calls
    ] == [
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
    ]
    assert output.context.active_result_id == (
        RESULT_ID
    )


def test_create_run_capture_has_four_steps() -> None:
    registry = FakeRegistry()

    output = make_orchestrator(
        registry=registry,
        workflow_name=(
            "create_run_and_capture"
        ),
    ).handle_turn(
        ChatTurnInput(
            user_message=(
                "Create this Explorer in MetaStock, "
                "run it, and capture the results."
            ),
            context=ChatContext(
                active_explorer_id=(
                    EXPLORER_ID
                )
            ),
        )
    )

    assert [
        name
        for name, _ in registry.calls
    ] == [
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
    ]
    assert output.route is (
        ChatRoute
        .CREATE_RUN_AND_READ_EXPLORER
    )


def test_workflow_stops_after_failure() -> None:
    registry = FakeRegistry(
        fail_on=(
            "run_selected_explorer_in_metastock"
        )
    )

    output = make_orchestrator(
        registry=registry,
        workflow_name="run_and_capture",
    ).handle_turn(
        ChatTurnInput(
            user_message=(
                "Run this Explorer and capture "
                "the results."
            ),
            context=ChatContext(
                active_explorer_id=(
                    EXPLORER_ID
                )
            ),
        )
    )

    assert [
        name
        for name, _ in registry.calls
    ] == [
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
    ]
    assert output.tool_result is not None
    assert output.tool_result.status is (
        ToolStatus.FAILED
    )
    assert "Workflow stopped" in (
        output.assistant_message
    )


def test_workflow_stops_after_blocked() -> None:
    registry = FakeRegistry(
        blocked_on=(
            "select_explorer_in_metastock"
        )
    )

    make_orchestrator(
        registry=registry,
        workflow_name="run_and_capture",
    ).handle_turn(
        ChatTurnInput(
            user_message=(
                "Run this Explorer and capture "
                "the results."
            ),
            context=ChatContext(
                active_explorer_id=(
                    EXPLORER_ID
                )
            ),
        )
    )

    assert [
        name
        for name, _ in registry.calls
    ] == [
        "select_explorer_in_metastock"
    ]


def test_negated_workflow_executes_nothing() -> None:
    registry = FakeRegistry()

    output = make_orchestrator(
        registry=registry,
        workflow_name="run_explorer",
    ).handle_turn(
        ChatTurnInput(
            user_message=(
                "Do not run this Explorer."
            ),
            context=ChatContext(
                active_explorer_id=(
                    EXPLORER_ID
                )
            ),
        )
    )

    assert registry.calls == []
    assert output.route is (
        ChatRoute.CLARIFY
    )
