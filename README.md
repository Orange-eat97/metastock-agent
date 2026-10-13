# Experiment: desktop application as passive frontend

Baseline: `d0307b47bc9743b4432b98823c7ccc2d9e1234ed`.

This branch **adds** a transport layer around the existing `ConversationApplicationService`.
It does not modify LangGraph, conversation persistence, RAG, ToolRegistry, or Automator.

## Install

From the repository root in the existing venv:

```powershell
python -m pip install "mcp>=2,<3"
$env:METASTOCK_RAG_REPO = "C:\GitHub\metastock-RAG-LLM"
$env:METASTOCK_AUTOMATOR_REPO = "C:\GitHub\metastock-automator"
# Also set the same Supabase state and OpenAI environment variables as scripts/chat_harness.py.
python -m scripts.start_gateway --transport stdio
```

The stdio process is normally spawned **by the MCP host**. It offers `agent_create_conversation`, `agent_chat`, and `agent_get_history`. This surface is tool-mediated; it does **not** automatically make a third-party app a passive frontend.

For a genuinely passive frontend, configure its custom chat backend (if supported) against the local, authenticated HTTP adapter:

```powershell
$env:METASTOCK_GATEWAY_TOKEN = "replace-with-a-random-private-token"
python -m scripts.start_gateway --transport http --port 8734
```

```
POST http://127.0.0.1:8734/conversations  {"title":"Demo"}
POST http://127.0.0.1:8734/chat           {"conversation_id":"...", "message":"Generate RSI explorer", "client_turn_id":"..."}
GET  http://127.0.0.1:8734/history/<conversation_id>
Authorization: Bearer <METASTOCK_GATEWAY_TOKEN>
```

Use one new `client_turn_id` (UUID) per new user turn, reuse it only for network retries. Sequential HTTP server avoids concurrent MetaStock actions.

## Checks

```powershell
python -m pytest -q test/mcp_adapters/test_agent_gateway.py
python -m pytest -q test/orchestration test/infrastructure/agent_state test/desktop_ui
```

No actual third-party passive desktop integration is claimed until a compatible host and credentials are supplied. No simulated token streaming has been added.
