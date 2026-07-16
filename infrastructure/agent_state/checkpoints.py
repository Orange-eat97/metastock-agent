from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Self

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
)
from langgraph.checkpoint.memory import (
    InMemorySaver,
)
from langgraph.checkpoint.postgres import (
    PostgresSaver,
)
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from infrastructure.agent_state.database import (
    AgentStateDatabaseSettings,
)


class CheckpointBackend(str, Enum):
    MEMORY = "memory"
    POSTGRES = "postgres"


class CheckpointStoreProtocol(Protocol):
    @property
    def saver(self) -> BaseCheckpointSaver:
        ...

    def setup(self) -> None:
        ...

    def delete_thread(
        self,
        thread_id: str,
    ) -> None:
        ...

    def close(self) -> None:
        ...


class InMemoryCheckpointStore:
    """
    Development and test checkpoint store.

    State is lost when the process exits. Production composition must use
    PostgresCheckpointStore.
    """

    def __init__(self) -> None:
        self._saver = InMemorySaver()

    @property
    def saver(self) -> BaseCheckpointSaver:
        return self._saver

    def setup(self) -> None:
        return None

    def delete_thread(
        self,
        thread_id: str,
    ) -> None:
        self._saver.delete_thread(
            str(thread_id)
        )

    def close(self) -> None:
        return None

    def __enter__(
        self,
    ) -> Self:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class PostgresCheckpointSettings:
    database_url: str
    pool_min_size: int = 1
    pool_max_size: int = 5
    pool_timeout_seconds: float = 10.0

    @classmethod
    def from_agent_state_settings(
        cls,
        settings: AgentStateDatabaseSettings,
    ) -> "PostgresCheckpointSettings":
        return cls(
            database_url=settings.database_url,
            pool_min_size=(
                settings.pool_min_size
            ),
            pool_max_size=(
                settings.pool_max_size
            ),
            pool_timeout_seconds=(
                settings.pool_timeout_seconds
            ),
        )


class PostgresCheckpointStore:
    """
    Dedicated LangGraph Postgres checkpoint pool.

    LangGraph requires autocommit connections with dict-row access. The
    existing agent-state pool deliberately uses ordinary transactions, so
    the two workloads must not share one ConnectionPool instance.
    """

    def __init__(
        self,
        settings: PostgresCheckpointSettings,
    ) -> None:
        self._settings = settings
        self._pool: ConnectionPool | None = (
            None
        )
        self._saver: (
            PostgresSaver | None
        ) = None

    @property
    def saver(self) -> BaseCheckpointSaver:
        if self._saver is None:
            raise RuntimeError(
                "Checkpoint store has not been "
                "opened."
            )

        return self._saver

    def open(self) -> None:
        if self._pool is not None:
            return

        pool = ConnectionPool(
            conninfo=(
                self._settings.database_url
            ),
            min_size=(
                self._settings.pool_min_size
            ),
            max_size=(
                self._settings.pool_max_size
            ),
            timeout=(
                self._settings
                .pool_timeout_seconds
            ),
            open=True,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                "prepare_threshold": 0,
                "application_name": (
                    "metastock-agent-checkpoints"
                ),
            },
        )

        try:
            pool.wait(
                timeout=(
                    self._settings
                    .pool_timeout_seconds
                )
            )
        except Exception:
            pool.close()
            raise

        self._pool = pool
        self._saver = PostgresSaver(pool)

    def setup(self) -> None:
        """
        Create/migrate LangGraph checkpoint tables.

        Call this through the explicit setup script during deployment. Do
        not call it for every application start or every conversation turn.
        """
        saver = self.saver

        if not isinstance(
            saver,
            PostgresSaver,
        ):
            raise RuntimeError(
                "Postgres saver is unavailable."
            )

        saver.setup()

    def delete_thread(
        self,
        thread_id: str,
    ) -> None:
        self.saver.delete_thread(
            str(thread_id)
        )

    def close(self) -> None:
        if self._pool is None:
            return

        self._pool.close()
        self._pool = None
        self._saver = None

    def __enter__(
        self,
    ) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()


def build_checkpoint_store(
    *,
    backend: CheckpointBackend | str,
    agent_state_settings: (
        AgentStateDatabaseSettings | None
    ) = None,
) -> CheckpointStoreProtocol:
    if isinstance(backend, CheckpointBackend):
        resolved_backend = backend
    else:
        resolved_backend = CheckpointBackend(
            str(backend).strip().casefold()
        )

    if (
        resolved_backend
        is CheckpointBackend.MEMORY
    ):
        return InMemoryCheckpointStore()

    if agent_state_settings is None:
        raise ValueError(
            "agent_state_settings is required "
            "for the postgres checkpoint backend."
        )

    return PostgresCheckpointStore(
        PostgresCheckpointSettings
        .from_agent_state_settings(
            agent_state_settings
        )
    )
