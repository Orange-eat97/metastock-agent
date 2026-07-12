from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from dotenv import load_dotenv
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


ENV_DATABASE_URL: Final[str] = "AGENT_STATE_DATABASE_URL"


class AgentStateConfigurationError(RuntimeError):
    """Raised when the agent-state database is not configured correctly."""


@dataclass(frozen=True, slots=True)
class AgentStateDatabaseSettings:
    database_url: str
    pool_min_size: int = 1
    pool_max_size: int = 5
    pool_timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls) -> "AgentStateDatabaseSettings":
        load_dotenv()

        database_url = os.getenv(ENV_DATABASE_URL, "").strip()

        if not database_url:
            raise AgentStateConfigurationError(
                f"{ENV_DATABASE_URL} is not configured."
            )

        if not database_url.startswith(
            ("postgresql://", "postgres://")
        ):
            raise AgentStateConfigurationError(
                f"{ENV_DATABASE_URL} must be a PostgreSQL connection URI."
            )

        return cls(database_url=database_url)


class AgentStateDatabase:
    """
    Owns the PostgreSQL connection pool for the agent-state database.

    This infrastructure object must remain below the repository/service
    layer. It must not be exposed to prompts, ToolRegistry arguments,
    ToolResult payloads, or the UI.
    """

    def __init__(
        self,
        settings: AgentStateDatabaseSettings,
    ) -> None:
        self._settings = settings
        self._pool: ConnectionPool | None = None

    @property
    def pool(self) -> ConnectionPool:
        if self._pool is None:
            raise RuntimeError(
                "Agent-state database pool has not been opened."
            )

        return self._pool

    def open(self) -> None:
        if self._pool is not None:
            return

        self._pool = ConnectionPool(
            conninfo=self._settings.database_url,
            min_size=self._settings.pool_min_size,
            max_size=self._settings.pool_max_size,
            timeout=self._settings.pool_timeout_seconds,
            open=True,
            kwargs={
                "autocommit": False,
                "application_name": "metastock-agent",
            },
        )

        self._pool.wait(
            timeout=self._settings.pool_timeout_seconds
        )

    def close(self) -> None:
        if self._pool is None:
            return

        self._pool.close()
        self._pool = None

    def health_check(self) -> dict[str, object]:
        with self.pool.connection() as connection:
            typed_connection: Connection = connection

            with typed_connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        current_database() AS database_name,
                        current_user AS database_user,
                        current_setting(
                            'application_name'
                        ) AS application_name,
                        version() AS postgres_version,
                        1 AS health_check
                    """
                )

                row = cursor.fetchone()

        if row is None or row["health_check"] != 1:
            raise RuntimeError(
                "Agent-state database health check failed."
            )

        return dict(row)

    def __enter__(self) -> "AgentStateDatabase":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()