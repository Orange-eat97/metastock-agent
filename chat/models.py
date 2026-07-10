from __future__ import annotations

from pydantic import BaseModel, Field

from tools.tool_contracts import ToolResult
from chat.routes import ChatRoute


class ChatContext(BaseModel):
    """
    Transient state for the current local chat session.

    This is deliberately not a Supabase conversation model. Milestone 3 keeps
    only the durable IDs needed to make the next deterministic tool call.
    """

    active_explorer_id: str | None = None
    active_service_log_id: str | None = None


class ChatTurnInput(BaseModel):
    user_message: str = Field(min_length=1)
    context: ChatContext = Field(default_factory=ChatContext)


class ChatTurnOutput(BaseModel):
    assistant_message: str
    route: ChatRoute
    context: ChatContext
    tool_result: ToolResult | None = None
