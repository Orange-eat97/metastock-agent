# Milestone 5 — Automator execution contract

Copy the included paths into the root of `metastock-agent`.

This milestone does not connect to or operate MetaStock. It adds:

- an `AutomatorClient` protocol;
- structured execution request/result models;
- an unavailable placeholder client;
- execution gates inside `run_explorer_in_metastock`;
- an enabled registry entry whose handler returns the correct gate result;
- unit and integration test updates.

Run the isolated gate tests:

```powershell
pytest test/test_automator_tool_gates.py -q
```

Run the live read-path test after the local RAG repository is configured:

```powershell
python -m test.test_tool_read_paths
```

Expected valid-Explorer execution result during Milestone 5:

```text
status=blocked
error.code=AUTOMATOR_NOT_CONFIGURED
```
