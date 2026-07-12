from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from chat.models import ChatContext
from chat.routes import ChatRoute
from tools.tool_contracts import ToolResult


class ConversationTurn(BaseModel):
    """One completed HumanMessage/AIMessage pair."""

    model_config = ConfigDict(frozen=True)

    user_content: str
    assistant_content: str

    route: ChatRoute | None = None
    context: ChatContext

    stream_id: UUID | None = None
    tool_call_ids: list[UUID]


class ExecuteConversationTurnResult(BaseModel):
    """Application-level result for one durable turn."""

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    stream_id: UUID
    client_turn_id: UUID

    assistant_message: str
    route: ChatRoute
    context: ChatContext
    tool_result: ToolResult | None

    replayed: bool = False