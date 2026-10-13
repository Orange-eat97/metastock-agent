# Experiment: passive desktop frontend, Jev tool/action choice

Baseline: `d0307b47bc9743b4432b98823c7ccc2d9e1234ed`.

Contains **the same thin conversation gateway** as experiment/mcp-agent-frontend.
Adds an opt-in Jev selection decorator in `orchestration/jev_action_selector.py` and environment-controlled wiring in `scripts/start_gateway.py`. No existing LangGraph/orchestration/services source files are changed.

Jev `Choice` selects an eligible **action schema**, or `__no_action__` / `__delegate__`.
Existing OpenAIConversationDriver still generates dialogue and tool arguments;
existing LangGraph action policy and deterministic workflows remain the execution gate.
Jev errors, low confidence, invalid choices and complex requests fall back to the unchanged driver.

```powershell
python -m pip install "mcp>=2,<3" typesafe-sdk
$env:METASTOCK_RAG_REPO = "C:\GitHub\metastock-RAG-LLM"
$env:METASTOCK_AUTOMATOR_REPO = "C:\GitHub\metastock-automator"
$env:TYPESAFE_API_KEY = "<your-key>"
$env:METASTOCK_JEV_ROUTING = "1"
$env:METASTOCK_JEV_MIN_CONFIDENCE = "0.80"
$env:METASTOCK_GATEWAY_TOKEN = "replace-with-a-random-private-token"
python -m scripts.start_gateway --transport http
```

The existing Supabase/OpenAI variables from `scripts/chat_harness.py` are also required.
`METASTOCK_JEV_ROUTING=0` bypasses Jev entirely and preserves standard routing.

```powershell
python -m pytest -q test/orchestration/test_jev_action_selector.py test/mcp_adapters/test_agent_gateway.py
python -m pytest -q test/orchestration test/infrastructure/agent_state
```

This is **not** evidence that Jev improves selection accuracy. It requires real credentials, model evaluation and end-to-end tests before enabling by default. No live TypeSafe inference, MetaStock GUI action or Supabase migration has been performed here.
