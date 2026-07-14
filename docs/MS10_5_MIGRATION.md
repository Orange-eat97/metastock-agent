# MS10.5 — Controlled static multi-tool workflows

## Scope

This batch enables the structured planner graph to execute three approved,
bounded workflows:

```text
run_explorer
    select_explorer_in_metastock
    run_selected_explorer_in_metastock

run_and_capture
    select_explorer_in_metastock
    run_selected_explorer_in_metastock
    read_metastock_explorer_results

create_run_and_capture
    create_explorer_in_metastock
    select_explorer_in_metastock
    run_selected_explorer_in_metastock
    read_metastock_explorer_results
```

Each workflow is sequential and contains at most four calls.

## Safety behavior

- Every step calls `ToolRegistry.execute(...)`.
- The existing `RecordingToolRegistry` records each step independently.
- No parallel execution.
- No automatic retries.
- No planner-generated step names.
- No automatic formula generation inside a workflow.
- Failed, blocked, and not-implemented results stop the workflow immediately.
- A negated action executes nothing.
- Result capture requires explicit result intent.
- `create_run_and_capture` requires explicit create, run, and result intent.

## Copy/overwrite

Copy these files into the repository root:

```text
chat/routes.py
orchestration/__init__.py
orchestration/context_resolver.py
orchestration/graph.py
orchestration/nodes.py
orchestration/planner.py
orchestration/state.py
orchestration/workflows.py
test/orchestration/test_structured_graph.py
test/orchestration/test_workflow_safety.py
test/orchestration/test_workflows.py
```

## Tests

```powershell
python -m pytest -q test/orchestration
python -m pytest -q test/chat
python -m pytest -q
```

## Structured-mode wiring

MS10.5 completes the missing multi-tool execution behavior. The durable harness
can now be switched from:

```python
LangGraphOrchestrator(
    recording_registry
)
```

to:

```python
LangGraphOrchestrator(
    recording_registry,
    planner=OpenAIPlanner(),
    explorer_name_resolver=explorer_name_resolver,
)
```

The exact `ExplorerNameResolver` must be constructed from the same RAG client
used by the application. Do not create a separate Supabase or RAG connection
inside the graph.

A production composition-root cleanup remains part of MS10.7. MS10.6 will add
LangGraph checkpoint persistence before that final cutover.
