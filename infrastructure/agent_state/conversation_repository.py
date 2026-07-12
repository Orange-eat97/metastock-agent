from __future__ import annotations

from typing import Final
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from infrastructure.agent_state.models import ConversationRecord


DEFAULT_LIST_LIMIT: Final[int] = 50
MAX_LIST_LIMIT: Final[int] = 200


class ConversationNotFoundError(LookupError):
    """Raised when a requested conversation does not exist."""


class ConversationRepository:
    """
    Persists application-owned conversation metadata.

    Message content is deliberately handled by
    PostgresChatMessageHistory rather than this repository.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(
        self,
        title: str | None = None,
    ) -> ConversationRecord:
        normalised_title = self._normalise_optional_title(title)

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.conversations (
                        title
                    )
                    VALUES (%s)
                    RETURNING
                        conversation_id,
                        title,
                        created_at,
                        updated_at,
                        archived_at
                    """,
                    (normalised_title,),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise RuntimeError(
                "Conversation insert returned no record."
            )

        return ConversationRecord.model_validate(row)

    def get(
        self,
        conversation_id: UUID,
    ) -> ConversationRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    """
                    SELECT
                        conversation_id,
                        title,
                        created_at,
                        updated_at,
                        archived_at
                    FROM public.conversations
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            return None

        return ConversationRecord.model_validate(row)

    def require(
        self,
        conversation_id: UUID,
    ) -> ConversationRecord:
        conversation = self.get(conversation_id)

        if conversation is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id} was not found."
            )

        return conversation

    def exists(
        self,
        conversation_id: UUID,
    ) -> bool:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM public.conversations
                        WHERE conversation_id = %s
                    )
                    """,
                    (conversation_id,),
                )

                row = cursor.fetchone()

            connection.commit()

        return bool(row and row[0])

    def list_recent(
        self,
        *,
        limit: int = DEFAULT_LIST_LIMIT,
        include_archived: bool = False,
    ) -> list[ConversationRecord]:
        validated_limit = self._validate_limit(limit)

        where_clause = (
            ""
            if include_archived
            else "WHERE archived_at IS NULL"
        )

        query = f"""
            SELECT
                conversation_id,
                title,
                created_at,
                updated_at,
                archived_at
            FROM public.conversations
            {where_clause}
            ORDER BY updated_at DESC
            LIMIT %s
        """

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    query,
                    (validated_limit,),
                )

                rows = cursor.fetchall()

            connection.commit()

        return [
            ConversationRecord.model_validate(row)
            for row in rows
        ]

    def rename(
        self,
        conversation_id: UUID,
        title: str | None,
    ) -> ConversationRecord:
        normalised_title = self._normalise_optional_title(title)

        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    """
                    UPDATE public.conversations
                    SET title = %s
                    WHERE conversation_id = %s
                    RETURNING
                        conversation_id,
                        title,
                        created_at,
                        updated_at,
                        archived_at
                    """,
                    (
                        normalised_title,
                        conversation_id,
                    ),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id} was not found."
            )

        return ConversationRecord.model_validate(row)

    def archive(
        self,
        conversation_id: UUID,
    ) -> ConversationRecord:
        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    """
                    UPDATE public.conversations
                    SET archived_at = COALESCE(
                        archived_at,
                        now()
                    )
                    WHERE conversation_id = %s
                    RETURNING
                        conversation_id,
                        title,
                        created_at,
                        updated_at,
                        archived_at
                    """,
                    (conversation_id,),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id} was not found."
            )

        return ConversationRecord.model_validate(row)

    def restore(
        self,
        conversation_id: UUID,
    ) -> ConversationRecord:
        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    """
                    UPDATE public.conversations
                    SET archived_at = NULL
                    WHERE conversation_id = %s
                    RETURNING
                        conversation_id,
                        title,
                        created_at,
                        updated_at,
                        archived_at
                    """,
                    (conversation_id,),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id} was not found."
            )

        return ConversationRecord.model_validate(row)

    def delete(
        self,
        conversation_id: UUID,
    ) -> bool:
        """
        Permanently delete a conversation.

        Related chat history, streams, and tool calls are deleted
        through the database foreign-key cascade.
        """
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM public.conversations
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )

                deleted = cursor.rowcount > 0

            connection.commit()

        return deleted

    @staticmethod
    def _normalise_optional_title(
        title: str | None,
    ) -> str | None:
        if title is None:
            return None

        normalised = title.strip()

        if not normalised:
            raise ValueError(
                "Conversation title cannot be blank."
            )

        return normalised

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise ValueError(
                "Conversation list limit must be between "
                f"1 and {MAX_LIST_LIMIT}."
            )

        return limit
    
    def clear_content(
        self,
        conversation_id: UUID,
    ) -> ConversationRecord:
        """
        Clear the conversation transcript and execution history.

        The conversation registry row and its title remain.

        Deleting turn_streams also deletes related tool_calls through
        the existing foreign-key cascade.
        """
        with self._pool.connection() as connection:
            with connection.cursor(
                row_factory=dict_row
            ) as cursor:
                cursor.execute(
                    """
                    SELECT conversation_id
                    FROM public.conversations
                    WHERE conversation_id = %s
                    FOR UPDATE
                    """,
                    (conversation_id,),
                )

                if cursor.fetchone() is None:
                    raise ConversationNotFoundError(
                        f"Conversation {conversation_id} "
                        "was not found."
                    )

                cursor.execute(
                    """
                    DELETE FROM public.chat_history
                    WHERE session_id = %s
                    """,
                    (conversation_id,),
                )

                cursor.execute(
                    """
                    DELETE FROM public.turn_streams
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )

                cursor.execute(
                    """
                    UPDATE public.conversations
                    SET updated_at = now()
                    WHERE conversation_id = %s
                    RETURNING
                        conversation_id,
                        title,
                        created_at,
                        updated_at,
                        archived_at
                    """,
                    (conversation_id,),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is None:
            raise RuntimeError(
                "Conversation clear returned no record."
            )

        return ConversationRecord.model_validate(row)