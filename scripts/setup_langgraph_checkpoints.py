from __future__ import annotations

import os

os.environ.setdefault(
    "LANGGRAPH_STRICT_MSGPACK",
    "true",
)

from infrastructure.agent_state import (
    AgentStateDatabaseSettings,
    PostgresCheckpointSettings,
    PostgresCheckpointStore,
)


def main() -> None:
    agent_settings = (
        AgentStateDatabaseSettings.from_environment()
    )
    checkpoint_settings = (
        PostgresCheckpointSettings.from_agent_state_settings(
            agent_settings
        )
    )

    with PostgresCheckpointStore(
        checkpoint_settings
    ) as store:
        store.setup()

    print("LangGraph checkpoint tables are ready.")


if __name__ == "__main__":
    main()
