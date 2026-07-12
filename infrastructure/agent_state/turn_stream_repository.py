from __future__ import annotations

from typing import Final
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from infrastructure.agent_state.models import (
    StreamAppendResult,
    TurnStreamRecord,
    TurnStreamStatus,
)

from infrastructure.agent_state.models import (
    StreamAppendResult,
    StreamStartResult,
    TurnStreamRecord,
    TurnStreamStatus,
)

STREAM_COLUMNS: Final[str] = """
    stream_id,
    conversation_id,
    client_turn_id,
    status,
    user_content,
    assistant_content,
    last_sequence,
    error_code,
    error_message,
    started_at,
    updated_at,
    completed_at
"""

class TurnStreamConflictError(RuntimeError):
    """
    Raised when one client_turn_id is reused with different content.
    """

class TurnStreamNotFoundError(LookupError):
    """Raised when a turn stream does not exist."""


class TurnStreamStateError(RuntimeError):
    """Raised when an operation is invalid for the stream state."""


class TurnStreamSequenceError(RuntimeError):
    """Raised when persisted stream deltas have a sequence gap."""


class TurnStreamRepository:
    """
    Persists in-progress and partial assistant responses.

    Completed HumanMessage and AIMessage objects are written to
    chat_history by the application service in a later milestone.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def start(
        self,
        *,
        conversation_id: UUID,
        client_turn_id: UUID,
        user_content: str,
    ) -> TurnStreamRecord:
        """
        Backward-compatible wrapper.

        New application code should prefer start_or_get() so it can tell
        whether the stream was newly created.
        """
        return self.start_or_get(
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            user_content=user_content,
        ).stream


    def start_or_get(
        self,
        *,
        conversation_id: UUID,
        client_turn_id: UUID,
        user_content: str,
    ) -> StreamStartResult:
        """
        Create one stream, or recover the existing stream for a retry.

        Reusing a client_turn_id with different user text is rejected.
        """
        normalised_user_content = user_content.strip()

        if not normalised_user_content:
            raise ValueError(
                "User content cannot be blank."
            )

        created = False

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO public.turn_streams (
                        conversation_id,
                        client_turn_id,
                        user_content
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (
                        conversation_id,
                        client_turn_id
                    )
                    DO NOTHING
                    RETURNING {STREAM_COLUMNS}
                    """,
                    (
                        conversation_id,
                        client_turn_id,
                        normalised_user_content,
                    ),
                )

                row = cursor.fetchone()

                if row is not None:
                    created = True
                else:
                    cursor.execute(
                        f"""
                        SELECT {STREAM_COLUMNS}
                        FROM public.turn_streams
                        WHERE conversation_id = %s
                        AND client_turn_id = %s
                        """,
                        (
                            conversation_id,
                            client_turn_id,
                        ),
                    )

                    row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise RuntimeError(
                "Could not create or reload the turn stream."
            )

        stream = TurnStreamRecord.model_validate(row)

        if stream.user_content != normalised_user_content:
            raise TurnStreamConflictError(
                "The client_turn_id already belongs to a "
                "different user message."
            )

        return StreamStartResult(
            created=created,
            stream=stream,
        )

    def get(
        self,
        stream_id: UUID,
    ) -> TurnStreamRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    SELECT {STREAM_COLUMNS}
                    FROM public.turn_streams
                    WHERE stream_id = %s
                    """,
                    (stream_id,),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            return None

        return TurnStreamRecord.model_validate(row)

    def require(
        self,
        stream_id: UUID,
    ) -> TurnStreamRecord:
        stream = self.get(stream_id)

        if stream is None:
            raise TurnStreamNotFoundError(
                f"Turn stream {stream_id} was not found."
            )

        return stream

    def append_delta(
        self,
        *,
        stream_id: UUID,
        sequence: int,
        content_delta: str,
    ) -> StreamAppendResult:
        """
        Append one assistant-output delta.

        Sequences must be contiguous:

            first persisted delta  -> sequence 1
            second persisted delta -> sequence 2

        Replaying the same or an older sequence is ignored
        idempotently. Skipping a sequence raises an error.
        """
        if sequence < 1:
            raise ValueError(
                "Stream sequence must be at least 1."
            )

        if not content_delta:
            raise ValueError(
                "Content delta cannot be empty."
            )

        expected_previous_sequence = sequence - 1

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    UPDATE public.turn_streams
                    SET
                        assistant_content =
                            assistant_content || %s,
                        last_sequence = %s
                    WHERE stream_id = %s
                      AND status = 'streaming'
                      AND last_sequence = %s
                    RETURNING {STREAM_COLUMNS}
                    """,
                    (
                        content_delta,
                        sequence,
                        stream_id,
                        expected_previous_sequence,
                    ),
                )

                updated_row = cursor.fetchone()

                if updated_row is not None:
                    connection.commit()

                    stream = TurnStreamRecord.model_validate(
                        updated_row
                    )

                    return StreamAppendResult(
                        applied=True,
                        stream=stream,
                    )

                cursor.execute(
                    f"""
                    SELECT {STREAM_COLUMNS}
                    FROM public.turn_streams
                    WHERE stream_id = %s
                    """,
                    (stream_id,),
                )

                current_row = cursor.fetchone()

            connection.commit()

        if current_row is None:
            raise TurnStreamNotFoundError(
                f"Turn stream {stream_id} was not found."
            )

        current = TurnStreamRecord.model_validate(
            current_row
        )

        if current.status != TurnStreamStatus.STREAMING:
            raise TurnStreamStateError(
                "Cannot append content to a stream with "
                f"status {current.status.value!r}."
            )

        if current.last_sequence >= sequence:
            return StreamAppendResult(
                applied=False,
                stream=current,
            )

        raise TurnStreamSequenceError(
            "Stream sequence gap detected. "
            f"Current sequence is {current.last_sequence}, "
            f"but received {sequence}."
        )

    def complete(
        self,
        *,
        stream_id: UUID,
        final_content: str | None = None,
    ) -> TurnStreamRecord:
        """
        Mark the stream completed.

        final_content can replace the persisted partial buffer with
        the controller's authoritative final assistant response.
        """
        normalised_final_content: str | None = None

        if final_content is not None:
            normalised_final_content = final_content.strip()

            if not normalised_final_content:
                raise ValueError(
                    "Final assistant content cannot be blank."
                )

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    UPDATE public.turn_streams
                    SET
                        assistant_content = COALESCE(
                            %s,
                            assistant_content
                        ),
                        status = 'completed',
                        completed_at = now(),
                        error_code = NULL,
                        error_message = NULL
                    WHERE stream_id = %s
                      AND status = 'streaming'
                    RETURNING {STREAM_COLUMNS}
                    """,
                    (
                        normalised_final_content,
                        stream_id,
                    ),
                )

                row = cursor.fetchone()

                if row is None:
                    cursor.execute(
                        f"""
                        SELECT {STREAM_COLUMNS}
                        FROM public.turn_streams
                        WHERE stream_id = %s
                        """,
                        (stream_id,),
                    )

                    row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise TurnStreamNotFoundError(
                f"Turn stream {stream_id} was not found."
            )

        stream = TurnStreamRecord.model_validate(row)

        if stream.status == TurnStreamStatus.COMPLETED:
            return stream

        raise TurnStreamStateError(
            "Only a streaming turn can be completed. "
            f"Current status is {stream.status.value!r}."
        )

    def fail(
        self,
        *,
        stream_id: UUID,
        error_code: str,
        error_message: str,
    ) -> TurnStreamRecord:
        normalised_code = error_code.strip()
        normalised_message = error_message.strip()

        if not normalised_code:
            raise ValueError(
                "Error code cannot be blank."
            )

        if not normalised_message:
            raise ValueError(
                "Error message cannot be blank."
            )

        return self._set_terminal_status(
            stream_id=stream_id,
            status=TurnStreamStatus.FAILED,
            error_code=normalised_code,
            error_message=normalised_message,
        )

    def cancel(
        self,
        *,
        stream_id: UUID,
        reason: str | None = None,
    ) -> TurnStreamRecord:
        normalised_reason = (
            reason.strip()
            if reason is not None
            else None
        )

        return self._set_terminal_status(
            stream_id=stream_id,
            status=TurnStreamStatus.CANCELLED,
            error_code="TURN_CANCELLED",
            error_message=(
                normalised_reason
                or "The turn was cancelled."
            ),
        )

    def list_for_conversation(
        self,
        conversation_id: UUID,
        *,
        limit: int = 50,
    ) -> list[TurnStreamRecord]:
        if not 1 <= limit <= 200:
            raise ValueError(
                "Stream list limit must be between 1 and 200."
            )

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    SELECT {STREAM_COLUMNS}
                    FROM public.turn_streams
                    WHERE conversation_id = %s
                    ORDER BY started_at DESC
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
            TurnStreamRecord.model_validate(row)
            for row in rows
        ]

    def get_active_for_conversation(
        self,
        conversation_id: UUID,
    ) -> TurnStreamRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    SELECT {STREAM_COLUMNS}
                    FROM public.turn_streams
                    WHERE conversation_id = %s
                      AND status = 'streaming'
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (conversation_id,),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            return None

        return TurnStreamRecord.model_validate(row)

    def _set_terminal_status(
        self,
        *,
        stream_id: UUID,
        status: TurnStreamStatus,
        error_code: str,
        error_message: str,
    ) -> TurnStreamRecord:
        if status not in {
            TurnStreamStatus.FAILED,
            TurnStreamStatus.CANCELLED,
        }:
            raise ValueError(
                "Unsupported terminal stream status."
            )

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    f"""
                    UPDATE public.turn_streams
                    SET
                        status = %s,
                        error_code = %s,
                        error_message = %s,
                        completed_at = now()
                    WHERE stream_id = %s
                      AND status = 'streaming'
                    RETURNING {STREAM_COLUMNS}
                    """,
                    (
                        status.value,
                        error_code,
                        error_message,
                        stream_id,
                    ),
                )

                row = cursor.fetchone()

                if row is None:
                    cursor.execute(
                        f"""
                        SELECT {STREAM_COLUMNS}
                        FROM public.turn_streams
                        WHERE stream_id = %s
                        """,
                        (stream_id,),
                    )

                    row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise TurnStreamNotFoundError(
                f"Turn stream {stream_id} was not found."
            )

        stream = TurnStreamRecord.model_validate(row)

        if stream.status == status:
            return stream

        raise TurnStreamStateError(
            "Only a streaming turn can enter status "
            f"{status.value!r}. Current status is "
            f"{stream.status.value!r}."
        )