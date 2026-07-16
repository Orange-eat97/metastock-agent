# MS10.3-10.4 — Structured planning and context resolution

## What this batch adds

```text
user turn
→ structured planner
→ decision validation
→ exact context/UUID resolution
→ one approved ToolRegistry call
→ explicit context update
→ ChatTurnOutput
```

The current deterministic parity graph is retained. `LangGraphOrchestrator`
selects its mode as follows:

```python
# Existing behavior
LangGraphOrchestrator(recording_registry)

# Structured MS10.3-10.4 behavior
LangGraphOrchestrator(
    recording_registry,
    planner=OpenAIPlanner(),
    explorer_name_resolver=explorer_name_resolver,
)
```

## Important stage boundary

Single-tool requests can execute in structured mode.

Multi-tool requests are recognized as named workflows but are **not executed**
in this batch. MS10.5 will add the static sequential workflow queue and then
perform the production structured-planner cutover. Keep the current durable
CLI on deterministic mode until that batch is installed.

## Copy/overwrite

Copy these into the repository root:

```text
chat/models.py
chat/routes.py
chat/result_mapper.py
services/recording_tool_registry.py
orchestration/
test/orchestration/
examples/
```

Do not remove the existing deterministic router or controller.

## Environment

The existing `OPENAI_API_KEY` is used by the official OpenAI client.

Optional model setting:

```env
METASTOCK_ORCHESTRATOR_MODEL=gpt-5-mini
```

`OpenAIPlanner` uses `client.responses.parse(..., text_format=PydanticModel)`.
The installed `openai` package must provide the Responses structured parse API.

## Checks

```powershell
python -m pytest -q test/orchestration
python -m pytest -q test/chat
python -m pytest -q
```

## Expected compatibility

- Existing `LangGraphOrchestrator(recording_registry)` remains deterministic.
- Existing chat and conversation services continue accepting the same turn
  interface.
- `ChatContext` gains only the optional `active_result_id`.
- `RecordingToolRegistry` now proxies read-only tool-catalog calls.
- Failed tool calls preserve the prior active context.
- Planner-provided unknown arguments are removed before registry validation.
- Explorer names use the existing exact-name resolver.
- Explorer/result/log UUIDs are validated before execution.
- Planner failure falls back to the existing deterministic router.
