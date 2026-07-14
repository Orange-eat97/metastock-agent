from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
)

from chat.models import (
    PlannerConversationMessage,
)


MAX_RECENT_PLANNER_MESSAGES = 12


def build_recent_planner_messages(
    messages: Sequence[BaseMessage],
    *,
    max_messages: int = (
        MAX_RECENT_PLANNER_MESSAGES
    ),
) -> list[PlannerConversationMessage]:
    """
    Convert completed LangChain transcript messages into a bounded planner
    window ordered from oldest to newest.

    System, tool, and unknown message types are deliberately excluded. The
    current user message is passed separately in ChatTurnInput.
    """
    if max_messages < 1:
        raise ValueError(
            "max_messages must be at least 1."
        )

    converted: list[
        PlannerConversationMessage
    ] = []

    for message in messages:
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue

        content = _message_text(
            message.content
        )

        if not content:
            continue

        converted.append(
            PlannerConversationMessage(
                role=role,
                content=content,
            )
        )

    return converted[-max_messages:]


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return str(content or "").strip()

    parts: list[str] = []

    for block in content:
        if isinstance(block, str):
            text = block.strip()
        elif isinstance(block, dict):
            text = str(
                block.get("text")
                or block.get("content")
                or ""
            ).strip()
        else:
            text = str(block or "").strip()

        if text:
            parts.append(text)

    return "\n".join(parts).strip()
