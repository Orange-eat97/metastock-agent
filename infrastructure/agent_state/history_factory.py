from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Final
from uuid import UUID

from langchain_core.messages import BaseMessage
from langchain_postgres import PostgresChatMessageHistory
from psycopg.pq import TransactionStatus
from psycopg_pool import ConnectionPool


CHAT_HISTORY_TABLE: Final[str] = "chat_history"


class LangChainHistoryFactory:
    """
    Creates LangChain-compatible history objects using pooled
    PostgreSQL connections.

    A PostgresChatMessageHistory object must not be retained after
    the context manager exits because its underlying connection has
    been returned to the pool.
    """

    def __init__(
        self,
        pool: ConnectionPool,
        table_name: str = CHAT_HISTORY_TABLE,
    ) -> None:
        if not table_name:
            raise ValueError(
                "History table name cannot be empty."
            )

        self._pool = pool
        self._table_name = table_name

    @contextmanager
    def open(
        self,
        conversation_id: UUID,
    ) -> Iterator[PostgresChatMessageHistory]:
        with self._pool.connection() as connection:
            history = PostgresChatMessageHistory(
                self._table_name,
                str(conversation_id),
                sync_connection=connection,
            )

            try:
                yield history
            finally:
                # A SELECT can leave a Psycopg transaction open.
                # Roll it back before returning the connection to
                # the pool. Inserts performed by LangChain commit
                # internally and will already be IDLE.
                if (
                    connection.info.transaction_status
                    != TransactionStatus.IDLE
                ):
                    connection.rollback()

    def get_messages(
        self,
        conversation_id: UUID,
    ) -> list[BaseMessage]:
        with self.open(conversation_id) as history:
            return history.get_messages()

    def add_messages(
        self,
        conversation_id: UUID,
        messages: Sequence[BaseMessage],
    ) -> None:
        message_list = list(messages)

        if not message_list:
            raise ValueError(
                "At least one message must be supplied."
            )

        with self.open(conversation_id) as history:
            history.add_messages(message_list)

    def clear(
        self,
        conversation_id: UUID,
    ) -> None:
        """
        Clear completed LangChain messages for one conversation.

        This intentionally keeps the conversation registry record,
        partial stream records, and tool-call history.
        """
        with self.open(conversation_id) as history:
            history.clear()