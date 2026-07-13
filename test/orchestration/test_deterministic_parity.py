from __future__ import annotations

from typing import Any

import pytest

from chat.controller import ChatTurnController
from chat.models import (
    ChatContext,
    ChatTurnInput,
)
from orchestration.orchestrator import (
    LangGraphOrchestrator,
)
from tools.tool_contracts import (
    ToolDisplay,
    ToolResult,
    ToolStatus,
)


class ParityRegistry:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        self.calls.append(
            (name, dict(arguments))
        )

        data: dict[str, Any] = {}

        if name == "generate_explorer":
            data = {
                "explorer": {
                    "explorer_id": "explorer-new",
                    "service_log_id": "log-new",
                }
            }
        elif name == "repair_explorer":
            data = {
                "explorer": {
                    "explorer_id": (
                        "explorer-repaired"
                    ),
                    "service_log_id": (
                        "log-repaired"
                    ),
                }
            }
        elif name == "get_explorer":
            data = {
                "explorer": {
                    "explorer_id": arguments[
                        "explorer_id"
                    ],
                    "service_log_id": (
                        "log-existing"
                    ),
                }
            }
        elif name == "get_rag_log":
            data = {
                "log_id": arguments["log_id"]
            }
        elif name == (
            "read_metastock_explorer_results"
        ):
            data = {
                "result_id": "result-1",
                "explorer_id": arguments[
                    "explorer_id"
                ],
            }

        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message=f"{name} passed",
            data=data,
            display=ToolDisplay(
                title=name,
                markdown=f"{name} markdown",
                severity="success",
            ),
        )


CASES = [
    ChatTurnInput(
        user_message=(
            "Find stocks where RSI is "
            "below 30"
        )
    ),
    ChatTurnInput(
        user_message=(
            "Fix the syntax error in "
            "this Explorer"
        ),
        context=ChatContext(
            active_explorer_id="explorer-1"
        ),
    ),
    ChatTurnInput(
        user_message=(
            "Show the current Explorer"
        ),
        context=ChatContext(
            active_explorer_id="explorer-1"
        ),
    ),
    ChatTurnInput(
        user_message=(
            "Show the RAG retrieval log"
        ),
        context=ChatContext(
            active_service_log_id="log-1"
        ),
    ),
    ChatTurnInput(
        user_message=(
            "Create this Explorer in "
            "MetaStock"
        ),
        context=ChatContext(
            active_explorer_id="explorer-1"
        ),
    ),
    ChatTurnInput(
        user_message=(
            "Select this Explorer in "
            "MetaStock"
        ),
        context=ChatContext(
            active_explorer_id="explorer-1"
        ),
    ),
    ChatTurnInput(
        user_message=(
            "Run the selected Explorer"
        ),
        context=ChatContext(
            active_explorer_id="explorer-1"
        ),
    ),
    ChatTurnInput(
        user_message=(
            "Run this Explorer in "
            "MetaStock"
        ),
        context=ChatContext(
            active_explorer_id="explorer-1"
        ),
    ),
    ChatTurnInput(
        user_message=(
            "Run this Explorer and "
            "capture the results"
        ),
        context=ChatContext(
            active_explorer_id="explorer-1"
        ),
    ),
    ChatTurnInput(
        user_message=(
            "Capture the Explorer results"
        ),
        context=ChatContext(
            active_explorer_id="explorer-1"
        ),
    ),
    ChatTurnInput(
        user_message="Hello"
    ),
    ChatTurnInput(
        user_message=(
            "Fix the syntax error in "
            "this Explorer"
        )
    ),
]


@pytest.mark.parametrize(
    "payload",
    CASES,
)
def test_langgraph_matches_legacy_controller(
    payload: ChatTurnInput,
) -> None:
    legacy_registry = ParityRegistry()
    graph_registry = ParityRegistry()

    legacy = ChatTurnController(
        legacy_registry
    )
    orchestrator = LangGraphOrchestrator(
        graph_registry
    )

    expected = legacy.handle_turn(
        payload
    )
    actual = orchestrator.handle_turn(
        payload
    )

    assert actual.model_dump(mode="json") == (
        expected.model_dump(mode="json")
    )
    assert graph_registry.calls == (
        legacy_registry.calls
    )


def test_run_sequence_preserves_tool_order() -> None:
    registry = ParityRegistry()
    orchestrator = LangGraphOrchestrator(
        registry
    )

    orchestrator.handle_turn(
        ChatTurnInput(
            user_message=(
                "Run this Explorer in "
                "MetaStock"
            ),
            context=ChatContext(
                active_explorer_id=(
                    "explorer-1"
                )
            ),
        )
    )

    assert [
        name
        for name, _ in registry.calls
    ] == [
        "select_explorer_in_metastock",
        (
            "run_selected_explorer_"
            "in_metastock"
        ),
    ]


def test_run_and_read_preserves_tool_order() -> None:
    registry = ParityRegistry()
    orchestrator = LangGraphOrchestrator(
        registry
    )

    orchestrator.handle_turn(
        ChatTurnInput(
            user_message=(
                "Run this Explorer and "
                "capture the results"
            ),
            context=ChatContext(
                active_explorer_id=(
                    "explorer-1"
                )
            ),
        )
    )

    assert [
        name
        for name, _ in registry.calls
    ] == [
        "select_explorer_in_metastock",
        (
            "run_selected_explorer_"
            "in_metastock"
        ),
        (
            "read_metastock_"
            "explorer_results"
        ),
    ]
