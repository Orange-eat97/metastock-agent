from __future__ import annotations

from chat.controller import ChatTurnController
from chat.models import ChatContext, ChatTurnInput
from chat.routes import ChatRoute
from test.chat.fakes import FakeRegistry
from tools.tool_contracts import ToolStatus


def test_generate_calls_registry_and_updates_context() -> None:
    registry = FakeRegistry()
    controller = ChatTurnController(registry)

    output = controller.handle_turn(
        ChatTurnInput(
            user_message="Find stocks where RSI is below 30",
        )
    )

    assert output.route is ChatRoute.GENERATE_EXPLORER
    assert registry.calls == [
        (
            "generate_explorer",
            {"user_query": "Find stocks where RSI is below 30"},
        )
    ]
    assert output.context.active_explorer_id == "explorer-new"
    assert output.context.active_service_log_id == "log-new"
    assert output.assistant_message == "Generated explorer markdown"


def test_repair_requires_active_explorer() -> None:
    registry = FakeRegistry()
    controller = ChatTurnController(registry)

    output = controller.handle_turn(
        ChatTurnInput(
            user_message="Fix the syntax error in this Explorer",
        )
    )

    assert output.route is ChatRoute.REPAIR_EXPLORER
    assert output.tool_result is None
    assert registry.calls == []


def test_repair_passes_current_id_and_instruction() -> None:
    registry = FakeRegistry()
    controller = ChatTurnController(registry)

    output = controller.handle_turn(
        ChatTurnInput(
            user_message="Fix the validation error in this Explorer",
            context=ChatContext(active_explorer_id="explorer-old"),
        )
    )

    assert registry.calls == [
        (
            "repair_explorer",
            {
                "explorer_id": "explorer-old",
                "repair_instruction": (
                    "Fix the validation error in this Explorer"
                ),
            },
        )
    ]
    assert output.context.active_explorer_id == "explorer-repaired"


def test_get_rag_log_uses_log_id_contract() -> None:
    registry = FakeRegistry()
    controller = ChatTurnController(registry)

    output = controller.handle_turn(
        ChatTurnInput(
            user_message="Show the RAG retrieval log",
            context=ChatContext(active_service_log_id="log-123"),
        )
    )

    assert registry.calls == [
        ("get_rag_log", {"log_id": "log-123"})
    ]
    assert output.route is ChatRoute.GET_RAG_LOG


def test_run_route_surfaces_structured_blocked_result() -> None:
    registry = FakeRegistry()
    controller = ChatTurnController(registry)

    output = controller.handle_turn(
        ChatTurnInput(
            user_message="Run this Explorer in MetaStock",
            context=ChatContext(active_explorer_id="explorer-123"),
        )
    )

    assert output.tool_result is not None
    assert output.tool_result.status is ToolStatus.BLOCKED
    assert output.context.active_explorer_id == "explorer-123"


def test_fallback_does_not_call_tool() -> None:
    registry = FakeRegistry()
    controller = ChatTurnController(registry)

    output = controller.handle_turn(
        ChatTurnInput(user_message="Hello")
    )

    assert output.route is ChatRoute.FALLBACK
    assert registry.calls == []
