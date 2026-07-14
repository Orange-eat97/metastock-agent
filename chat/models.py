from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from chat.routes import ChatRoute
from tools.tool_contracts import ToolResult


class ChatContext(BaseModel):
    active_explorer_id: str | None = None
    active_result_id: str | None = None
    active_service_log_id: str | None = None


class PlannerConversationMessage(BaseModel):
    """One completed transcript message supplied to the turn planner."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12_000)


class ChatTurnInput(BaseModel):
    user_message: str = Field(min_length=1)
    context: ChatContext = Field(
        default_factory=ChatContext
    )

    # Bounded transcript context. LangGraphOrchestrator passes this through
    # StateGraph runtime context, not checkpointed graph state.
    recent_messages: list[
        PlannerConversationMessage
    ] = Field(
        default_factory=list,
        max_length=12,
    )

    # ConversationApplicationService sets this to conversation_id.
    # LangGraph uses the same UUID string as configurable.thread_id.
    thread_id: UUID | None = None


class ChatTurnOutput(BaseModel):
    assistant_message: str
    route: ChatRoute
    context: ChatContext
    tool_result: ToolResult | None = None
