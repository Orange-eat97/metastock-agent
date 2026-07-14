from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)

from services.planner_history import (
    build_recent_planner_messages,
)


def test_builds_user_assistant_window() -> None:
    messages = [
        SystemMessage(content="ignored"),
        HumanMessage(content="Generate RSI scan"),
        AIMessage(content="Explorer created"),
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


def test_keeps_only_latest_bounded_messages() -> None:
    messages = [
        HumanMessage(content=f"message-{index}")
        for index in range(20)
    ]

    result = build_recent_planner_messages(
        messages,
        max_messages=4,
    )

    assert [
        item.content
        for item in result
    ] == [
        "message-16",
        "message-17",
        "message-18",
        "message-19",
    ]
