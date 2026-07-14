# MS10.6 — LangGraph checkpoint persistence

## Scope

This batch keeps the existing LangChain/Postgres chat transcript and adds a
separate LangGraph checkpoint layer.

```text
chat_history
    completed human/assistant transcript

checkpoints / checkpoint_blobs / checkpoint_writes
    LangGraph execution state
```

`conversation_id` is used verbatim as LangGraph `thread_id`.

## Install

Copy the bundle contents into the repository root, overwriting matching files.

Then run the idempotent source patch:

```powershell
python -m scripts.apply_ms10_6
```

Install the new dependency:

```powershell
pip install -r requirements.txt
```

## Initialize Postgres checkpoint tables once

The setup operation performs LangGraph's checkpoint migrations. Run it once for
each agent-state database, and again only after a checkpoint package upgrade
that requires migrations:

```powershell
$env:LANGGRAPH_STRICT_MSGPACK = "true"
python -m scripts.setup_langgraph_checkpoints
```

Do not call `setup()` during every app start or every chat turn.

## Runtime wiring

The final composition-root cleanup belongs to MS10.7. Until then, construct a
store at application startup and keep it open for the lifetime of the app:

```python
from infrastructure.agent_state import (
    AgentStateDatabaseSettings,
    PostgresCheckpointSettings,
    PostgresCheckpointStore,
)

agent_settings = (
    AgentStateDatabaseSettings
    .from_environment()
)
checkpoint_settings = (
    PostgresCheckpointSettings
    .from_agent_state_settings(
        agent_settings
    )
)

with PostgresCheckpointStore(
    checkpoint_settings
) as checkpoints:
    orchestrator = LangGraphOrchestrator(
        recording_registry,
        planner=OpenAIPlanner(),
        explorer_name_resolver=(
            explorer_name_resolver
        ),
        checkpointer=checkpoints.saver,
    )
```

Pass the same `checkpoints` object to
`ConversationApplicationService(checkpoints=checkpoints)`.

The service patch makes every turn pass:

```python
ChatTurnInput(
    ...,
    thread_id=conversation_id,
)
```

It also deletes the corresponding checkpoint thread before clearing or deleting
a conversation.

## Connection-pool separation

Do not pass the existing `AgentStateDatabase.pool` to `PostgresSaver`.

The existing repository pool uses normal transactions. LangGraph's Postgres
saver requires a pool configured with:

```text
autocommit=True
row_factory=dict_row
prepare_threshold=0
```

`PostgresCheckpointStore` owns this dedicated pool while still using the same
agent-state database URI.

## Tests

```powershell
python -m pytest -q test/orchestration
python -m pytest -q test/infrastructure/agent_state
python -m pytest -q test/chat
python -m pytest -q
```

## Development mode

Use `InMemoryCheckpointStore` only for local debugging and unit tests. It loses
all state when the process exits.
