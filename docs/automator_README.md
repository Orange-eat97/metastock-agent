# Milestone 6 — Local Automator execution

This bundle modifies both repositories.

## metastock-automator

Copy:

```text
main/automator_service.py
main/test/test_automator_service.py
```

## metastock-agent

Replace/add:

```text
services/automator_client.py
scripts/chat_harness.py
test/test_local_automator_client.py
test/test_automator_tool_gates_additions.py
```

Set:

```powershell
$env:METASTOCK_RAG_REPO = "C:\GitHub\metastock-RAG-LLM"
$env:METASTOCK_AUTOMATOR_REPO = "C:\GitHub\metastock-automator\main"
```

MetaStock must already be open. The current Automator connects to an existing
`Main - MetaStock` window, creates a new Explorer, and then runs it.

Run tests:

```powershell
cd C:\GitHub\metastock-agent
pytest test/test_automator_tool_gates.py test/test_automator_tool_gates_additions.py test/test_local_automator_client.py -q

cd C:\GitHub\metastock-automator\main
pytest test/test_automator_service.py -q
```

Start the harness:

```powershell
cd C:\GitHub\metastock-agent
python -m scripts.chat_harness
```

Then generate or open a valid Explorer and enter:

```text
Run this Explorer in MetaStock
```

This milestone does not overwrite same-name Explorers, parse result rows, store
execution runs, take screenshots, or perform backtests.
