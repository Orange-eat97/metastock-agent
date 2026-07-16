# MS10.1-10.2 LangGraph parity batch

## Scope

This batch introduces LangGraph without changing current behavior.

The graph intentionally has one transitional node that delegates one complete
turn to the existing `ChatTurnController`. This preserves:

- `DeterministicChatRouter`;
- current missing-context responses;
- current controller-level select/run/read sequences;
- `ToolRegistry.execute(...)`;
- `RecordingToolRegistry` audit persistence;
- `ChatTurnInput` and `ChatTurnOutput`;
- current conversation persistence.

The structured LLM planner and explicit context resolver belong to the next
merged batch, MS10.3-10.4.

## Copy

Copy these directories into the repository root:

```text
orchestration/
test/orchestration/
```

Add this line to `requirements.txt`:

```text
langgraph
```

## Optional harness switch

Apply `patches/chat_harness.patch` to run the durable CLI through LangGraph.

The new orchestrator implements the same `handle_turn(ChatTurnInput) ->
ChatTurnOutput` protocol expected by `ConversationApplicationService`.

## Install

```powershell
pip install -U langgraph
```

Or reinstall the repository requirements after adding `langgraph`.

## Checks

```powershell
python -m pytest -q test/orchestration
python -m pytest -q test/chat
python -m pytest -q
```

The key parity check compares the JSON output and exact registry call sequence
from `ChatTurnController` against `LangGraphOrchestrator`.

## Expected behavior

For this batch, LangGraph does not yet select tools itself. It provides the
runtime shell while the existing deterministic controller remains authoritative.
This is intentional: it establishes a low-risk substitution point before
MS10.3-10.4 replaces deterministic routing with structured LLM planning.
