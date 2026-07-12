from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConversationRecord(BaseModel):
    """Application-owned conversation metadata."""

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class TurnStreamStatus(str, Enum):
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TurnStreamRecord(BaseModel):
    """Persisted state for one user/assistant turn."""

    model_config = ConfigDict(frozen=True)

    stream_id: UUID
    conversation_id: UUID
    client_turn_id: UUID

    status: TurnStreamStatus

    user_content: str
    assistant_content: str
    last_sequence: int

    error_code: str | None
    error_message: str | None

    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class StreamAppendResult(BaseModel):
    """
    Result of attempting to append one persisted stream delta.

    applied=False normally means that the same or an older sequence
    was submitted again and was ignored idempotently.
    """

    model_config = ConfigDict(frozen=True)

    applied: bool
    stream: TurnStreamRecord

class StreamStartResult(BaseModel):
    """
    Result of creating or recovering a client turn.

    created=False means the supplied client_turn_id already existed.
    """

    model_config = ConfigDict(frozen=True)

    created: bool
    stream: TurnStreamRecord


class ToolCallStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolCallRecord(BaseModel):
    """Persisted record of one ToolRegistry invocation."""

    model_config = ConfigDict(frozen=True)

    tool_call_id: UUID
    conversation_id: UUID
    stream_id: UUID

    provider_call_id: str | None
    ordinal: int

    tool_name: str
    status: ToolCallStatus

    arguments_json: dict[str, Any]
    result_json: dict[str, Any] | None

    error_code: str | None
    error_message: str | None

    started_at: datetime
    finished_at: datetime | None