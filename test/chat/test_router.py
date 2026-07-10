from __future__ import annotations

import pytest

from chat.router import DeterministicChatRouter
from chat.routes import ChatRoute


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Find stocks where RSI is below 30",
            ChatRoute.GENERATE_EXPLORER,
        ),
        (
            "Create an Explorer for a 20-day breakout",
            ChatRoute.GENERATE_EXPLORER,
        ),
        (
            "Fix the syntax error in this Explorer",
            ChatRoute.REPAIR_EXPLORER,
        ),
        (
            "Show the current Explorer",
            ChatRoute.GET_EXPLORER,
        ),
        (
            "Show me the RAG retrieval log",
            ChatRoute.GET_RAG_LOG,
        ),
        (
            "Run this Explorer in MetaStock",
            ChatRoute.RUN_EXPLORER,
        ),
        (
            "What can you do?",
            ChatRoute.FALLBACK,
        ),
    ],
)
def test_route(message: str, expected: ChatRoute) -> None:
    router = DeterministicChatRouter()
    assert router.route(message) is expected


def test_log_route_has_precedence_over_get_explorer() -> None:
    router = DeterministicChatRouter()
    assert (
        router.route("Show the RAG log for the current Explorer")
        is ChatRoute.GET_RAG_LOG
    )
