# Experiment: host-controlled tool routing with MCP

Baseline: `d0307b47bc9743b4432b98823c7ccc2d9e1234ed`.

This adds an MCP adapter for **existing public ToolRegistry tools only**.
LangGraph and all business logic remain untouched; the external host chooses tools.

```powershell
python -m pip install "mcp>=2,<3"
$env:METASTOCK_RAG_REPO = "C:\GitHub\metastock-RAG-LLM"
$env:METASTOCK_AUTOMATOR_REPO = "C:\GitHub\metastock-automator"
python -m scripts.start_tool_mcp --audit logs/mcp_calls.jsonl
```

Normally configure the desktop MCP client to run `python -m scripts.start_tool_mcp` from the repository root; it launches the stdio process for you. Do **not** print to stdout from the server.

The public manifest is automatically taken from `registry.list_conversation_tools()`. Internal UI steps are **not** published. Host-side tool calls are recorded in a separate append-only JSONL file (start/finish) without raw arguments or result bodies. The existing per-turn ToolCallRepository is not changed.

**Important history limitation:** standard MCP tools do not supply the host's entire chat history. This prototype does not falsely claim to persist a complete external conversation. To meet that requirement, the chosen desktop host must supply a chat-event sync mechanism; the host/application is not yet specified. Selecting tools with a desktop LLM is not equivalent to preserving existing LangGraph dialogue history.

```powershell
python -m pytest -q test/mcp_adapters/test_tool_bridge.py
python -m pytest -q test/orchestration test/services
```
