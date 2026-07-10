# Milestone 3 — Minimal Backend Chat Harness

Copy these directories into the repository root:

```text
chat/
scripts/chat_harness.py
test/chat/
```

No existing repository file must be modified for the first implementation.

## Install/test

The repository already uses Pydantic. Add pytest only if it is not installed:

```powershell
pip install pytest
pytest test/chat -q
```

## Run the real harness

PowerShell:

```powershell
$env:METASTOCK_RAG_REPO = "C:\GitHub\metastock-RAG-LLM"
python -m scripts.chat_harness
```

Optional seeded context:

```powershell
python -m scripts.chat_harness `
  --explorer-id "<explorer_outputs.id>" `
  --service-log-id "<rag_service_logs.log_id>"
```

Example messages:

```text
Find stocks where RSI is below 30 and close is above the 50-day moving average
Show the current Explorer
Show the RAG retrieval log
Fix the validation error in this Explorer
Run this Explorer in MetaStock
```

The final command should return the existing structured BLOCKED result because the
registry intentionally keeps `run_explorer_in_metastock` disabled.
