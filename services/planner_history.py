from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
)

from chat.models import (
    MAX_RECENT_CONVERSATION_MESSAGES,
    MAX_RECENT_MESSAGE_CHARS,
    PlannerConversationMessage,
)
import re


MAX_RECENT_PLANNER_MESSAGES = (
    MAX_RECENT_CONVERSATION_MESSAGES
)

_HIDDEN_ASSISTANT_CONTEXT_LINE = re.compile(
    r"^\s*-\s*(?:"
    r"Explorer ID"
    r"|MetaStock state"
    r"|Columns"
    r")\s*:",
    re.IGNORECASE,
)


def build_recent_planner_messages(
    messages: Sequence[BaseMessage],
    *,
    max_messages: int = (
        MAX_RECENT_PLANNER_MESSAGES
    ),
) -> list[PlannerConversationMessage]:
    """
    Build the small conversation-model context window.

    Only completed HumanMessage and AIMessage entries are included. The current
    user message is supplied separately. System, tool, and unknown messages are
    excluded.
    """
    if max_messages < 1:
        raise ValueError(
            "max_messages must be at least 1."
        )

    if (
        max_messages
        > MAX_RECENT_CONVERSATION_MESSAGES
    ):
        raise ValueError(
            "max_messages cannot exceed "
            f"{MAX_RECENT_CONVERSATION_MESSAGES}."
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

        if role == "assistant":
            content = _sanitize_assistant_context(
                content
            )

        if not content:
            continue

        converted.append(
            PlannerConversationMessage(
                role=role,
                content=_truncate_message(
                    content
                ),
            )
        )

    return converted[-max_messages:]


def _sanitize_assistant_context(
    content: str,
) -> str:
    """
    Remove internal or excessive Explorer fields before an old
    assistant message is supplied to the conversation model.
    """
    kept_lines = [
        line
        for line in content.splitlines()
        if not _HIDDEN_ASSISTANT_CONTEXT_LINE.match(
            line
        )
    ]

    return "\n".join(kept_lines).strip()


def _truncate_message(
    content: str,
) -> str:
    cleaned = content.strip()

    if len(cleaned) <= MAX_RECENT_MESSAGE_CHARS:
        return cleaned

    return (
        cleaned[
            : MAX_RECENT_MESSAGE_CHARS - 1
        ]
        + "…"
    )


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
