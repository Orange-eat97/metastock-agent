from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from chat.routes import ChatRoute
from tools.tool_contracts import ToolResult


MAX_RECENT_CONVERSATION_MESSAGES = 5
MAX_RECENT_MESSAGE_CHARS = 4_000


class ChatContext(BaseModel):
    active_explorer_id: str | None = None

    # This is conversational orchestration state, not a claim about MetaStock's
    # global catalogue. It records only what the current workflow has proved
    # about the active Explorer.
    active_explorer_metastock_state: Literal[
        "unknown",
        "not_created",
        "created",
    ] = "unknown"

    active_result_id: str | None = None
    active_service_log_id: str | None = None


class PlannerConversationMessage(BaseModel):
    """
    One completed transcript message supplied to the conversation model.

    No RAG cards, raw tool payloads, database rows, or checkpoint state are
    stored in this DTO.
    """

    role: Literal["user", "assistant"]
    content: str = Field(
        min_length=1,
        max_length=MAX_RECENT_MESSAGE_CHARS,
    )


class ChatTurnInput(BaseModel):
    user_message: str = Field(min_length=1)
    context: ChatContext = Field(
        default_factory=ChatContext
    )

    recent_messages: list[
        PlannerConversationMessage
    ] = Field(
        default_factory=list,
        max_length=MAX_RECENT_CONVERSATION_MESSAGES,
    )

    thread_id: UUID | None = None


class ChatTurnOutput(BaseModel):
    assistant_message: str
    route: ChatRoute
    context: ChatContext
    tool_result: ToolResult | None = None
