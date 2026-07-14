# MS10.7 — Production cutover and stabilization

## Scope

This batch centralizes application wiring and makes LangGraph the default
orchestrator while retaining the legacy controller as an explicit rollback
mode.

The composition root explicitly constructs:

```text
LocalRagClient
ExplorerRepository
ExplorerReviewWorkflow
ExplorerToolService
MetaStockResultToolService
ToolRegistry
ExplorerNameResolver
OpenAIPlanner
LangGraph checkpointer
LangGraphOrchestrator
ConversationApplicationService
```

No graph node creates RAG, Automator, database, or OpenAI clients.

## Copy

Copy the bundle into the repository root and overwrite matching files:

```text
application/
scripts/chat_harness.py
scripts/setup_langgraph_checkpoints.py
test/application/
```

The old `examples/structured_orchestrator_factory.py` is now redundant and may
be deleted.

## Production defaults

```env
AGENT_ORCHESTRATOR=langgraph
AGENT_CHECKPOINT_BACKEND=postgres
LANGGRAPH_STRICT_MSGPACK=true
```

Optional:

```env
METASTOCK_ORCHESTRATOR_MODEL=gpt-5-mini
```

The temporary planner-error fallback remains enabled for one stabilization
cycle. Disable it explicitly with:

```powershell
python -m scripts.chat_harness `
  --disable-deterministic-fallback
```

## Rollback

```powershell
python -m scripts.chat_harness `
  --orchestrator legacy
```

Legacy mode uses the same ToolRegistry and business services. Do not remove
`ToolRegistry`.

## Checkpoint setup

Do not run setup on every start. Run it only for a new agent-state database or
when a deliberate checkpoint package upgrade requires migrations:

```powershell
python -m scripts.setup_langgraph_checkpoints
```

## Tests

```powershell
python -m pytest -q test/application
python -m pytest -q test/orchestration
python -m pytest -q test/infrastructure/agent_state
python -m pytest -q test/chat
python -m pytest -q
```

## Local smoke test without MetaStock

```powershell
$env:AGENT_ORCHESTRATOR = "langgraph"
$env:AGENT_CHECKPOINT_BACKEND = "postgres"

python -m scripts.chat_harness `
  --rag-repo "C:\GitHub\metastock-RAG-LLM" `
  --new-conversation `
  --title "MS10 LangGraph smoke test"
```

Suggested prompts:

```text
Find stocks where RSI is below 30 and close is above the 50-day moving average.
Show the current Explorer.
Show the RAG retrieval log.
```

## Real Automator smoke test

Run only with MetaStock open and logged in:

```powershell
$env:METASTOCK_AUTOMATOR_REPO = "C:\GitHub\metastock-automator\main"

python -m scripts.chat_harness `
  --rag-repo "C:\GitHub\metastock-RAG-LLM" `
  --new-conversation `
  --title "MS10 Automator smoke test"
```

After generating or opening a valid stored Explorer:

```text
Run this Explorer.
Run this Explorer and capture the results.
```

Verify that recorded tool calls are sequential and the final capture updates
`active_result_id`.

## Stabilization exit gate

Keep legacy mode for one stabilization cycle. Remove the deterministic router
only after all of the following are true:

```text
- full test suite passes;
- production LangGraph is the default;
- same-conversation checkpoint resume passes;
- separate conversations do not leak IDs;
- real RAG generation smoke test passes;
- real name resolution smoke test passes;
- real select/run boundary smoke test passes;
- real run-and-capture smoke test passes;
- no rollback to legacy mode is required during stabilization.
```

Even after legacy routing is removed, retain:

```text
ToolRegistry
ToolResult
Pydantic tool inputs
RecordingToolRegistry
conversation transcript persistence
checkpoint persistence
```
