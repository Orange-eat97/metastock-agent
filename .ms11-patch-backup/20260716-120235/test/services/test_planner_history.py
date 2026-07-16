from __future__ import annotations

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)

from chat.models import (
    MAX_RECENT_MESSAGE_CHARS,
)
from services.planner_history import (
    MAX_RECENT_PLANNER_MESSAGES,
    build_recent_planner_messages,
)


def test_builds_user_assistant_window() -> None:
    messages = [
        SystemMessage(content="ignored"),
        HumanMessage(
            content="Generate RSI scan"
        ),
        AIMessage(
            content="Explorer created"
        ),
    ]

    result = build_recent_planner_messages(
        messages
    )

    assert [
        item.model_dump()
        for item in result
    ] == [
        {
            "role": "user",
            "content": "Generate RSI scan",
        },
        {
            "role": "assistant",
            "content": "Explorer created",
        },
    ]


def test_default_window_is_latest_five_messages() -> None:
    messages = [
        HumanMessage(
            content=f"message-{index}"
        )
        for index in range(9)
    ]

    result = build_recent_planner_messages(
        messages
    )

    assert MAX_RECENT_PLANNER_MESSAGES == 5
    assert [
        item.content
        for item in result
    ] == [
        "message-4",
        "message-5",
        "message-6",
        "message-7",
        "message-8",
    ]


def test_rejects_window_larger_than_five() -> None:
    with pytest.raises(
        ValueError,
        match="cannot exceed 5",
    ):
        build_recent_planner_messages(
            [
                HumanMessage(
                    content="hello"
                )
            ],
            max_messages=6,
        )


def test_truncates_large_message() -> None:
    result = build_recent_planner_messages(
        [
            AIMessage(
                content=(
                    "x"
                    * (
                        MAX_RECENT_MESSAGE_CHARS
                        + 100
                    )
                )
            )
        ]
    )

    assert len(
        result[0].content
    ) == MAX_RECENT_MESSAGE_CHARS
    assert result[
        0
    ].content.endswith("…")
