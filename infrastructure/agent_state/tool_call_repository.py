from __future__ import annotations

from typing import Final
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from infrastructure.agent_state.models import (
    ToolCallRecord,
    ToolCallStatus,
)
from tools.tool_contracts import ToolResult


TOOL_CALL_COLUMNS: Final[str] = """
    tool_call_id,
    conversation_id,
    stream_id,
    provider_call_id,
    ordinal,
    tool_name,
    status,
    arguments_json,
    result_json,
    error_code,
    error_message,
    started_at,
    finished_at
"""


class ToolCallNotFoundError(LookupError):
    """Raised when a tool-call record cannot be found."""


class ToolCallStateError(RuntimeError):
    """Raised for an invalid tool-call state transition."""


class ToolCallRepository:
    """Persists ToolRegistry invocation lifecycle records."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def start(
        self,
        *,
        conversation_id: UUID,
        stream_id: UUID,
        ordinal: int,
        tool_name: str,
        arguments: dict[str, object],
        provider_call_id: str | None = None,
    ) -> ToolCallRecord:
        normalised_name = tool_name.strip()

        if not normalised_name:
            raise ValueError("Tool name cannot be blank.")

        if ordinal < 0:
            raise ValueError(
                "Tool-call ordinal cannot be negative."
            )

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO public.tool_calls (
                        conversation_id,
                        stream_id,
                        provider_call_id,
                        ordinal,
                        tool_name,
                        arguments_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING {TOOL_CALL_COLUMNS}
                    """,
                    (
                        conversation_id,
                        stream_id,
                        provider_call_id,
                        ordinal,
                        normalised_name,
                        Jsonb(arguments),
                    ),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise RuntimeError(
                "Tool-call insert returned no record."
            )

        return ToolCallRecord.model_validate(row)

    def finish(
        self,
        *,
        tool_call_id: UUID,
        result: ToolResult,
    ) -> ToolCallRecord:
        status = (
            ToolCallStatus.SUCCEEDED
            if result.ok
            else ToolCallStatus.FAILED
        )

        error_code = (
            result.error.code
            if result.error is not None
            else None
        )
        error_message = (
            result.error.message
            if result.error is not None
            else None
        )

        result_payload = result.model_dump(mode="json")

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    UPDATE public.tool_calls
                    SET
                        status = %s,
                        result_json = %s,
                        error_code = %s,
                        error_message = %s,
                        finished_at = now()
                    WHERE tool_call_id = %s
                      AND status = 'running'
                    RETURNING {TOOL_CALL_COLUMNS}
                    """,
                    (
                        status.value,
                        Jsonb(result_payload),
                        error_code,
                        error_message,
                        tool_call_id,
                    ),
                )

                row = cursor.fetchone()

                if row is None:
                    cursor.execute(
                        f"""
                        SELECT {TOOL_CALL_COLUMNS}
                        FROM public.tool_calls
                        WHERE tool_call_id = %s
                        """,
                        (tool_call_id,),
                    )

                    row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise ToolCallNotFoundError(
                f"Tool call {tool_call_id} was not found."
            )

        record = ToolCallRecord.model_validate(row)

        if record.status == status:
            return record

        raise ToolCallStateError(
            "Only a running tool call can be finished. "
            f"Current status is {record.status.value!r}."
        )

    def fail_exception(
        self,
        *,
        tool_call_id: UUID,
        exception: Exception,
    ) -> ToolCallRecord:
        error_message = str(exception).strip()

        if not error_message:
            error_message = type(exception).__name__

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    UPDATE public.tool_calls
                    SET
                        status = 'failed',
                        error_code = %s,
                        error_message = %s,
                        finished_at = now()
                    WHERE tool_call_id = %s
                      AND status = 'running'
                    RETURNING {TOOL_CALL_COLUMNS}
                    """,
                    (
                        type(exception).__name__,
                        error_message,
                        tool_call_id,
                    ),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise ToolCallStateError(
                "Could not mark the tool call as failed."
            )

        return ToolCallRecord.model_validate(row)

    def list_for_stream(
        self,
        stream_id: UUID,
    ) -> list[ToolCallRecord]:
        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    SELECT {TOOL_CALL_COLUMNS}
                    FROM public.tool_calls
                    WHERE stream_id = %s
                    ORDER BY ordinal
                    """,
                    (stream_id,),
                )

                rows = cursor.fetchall()

            connection.commit()

        return [
            ToolCallRecord.model_validate(row)
            for row in rows
        ]

    def list_for_conversation(
        self,
        conversation_id: UUID,
        *,
        limit: int = 100,
    ) -> list[ToolCallRecord]:
        if not 1 <= limit <= 500:
            raise ValueError(
                "Tool-call list limit must be between "
                "1 and 500."
            )

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    SELECT {TOOL_CALL_COLUMNS}
                    FROM public.tool_calls
                    WHERE conversation_id = %s
                    ORDER BY started_at DESC, ordinal DESC
                    LIMIT %s
                    """,
                    (
                        conversation_id,
                        limit,
                    ),
                )

                rows = cursor.fetchall()

            connection.commit()

        return [
            ToolCallRecord.model_validate(row)
            for row in rows
        ]