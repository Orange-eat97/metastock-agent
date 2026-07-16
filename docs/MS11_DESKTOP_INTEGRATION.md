# MS11 desktop integration

Extract this overlay into the root of `C:\GitHub\metastock-agent` on an MS11
branch created from `ms10-langgraph-orchestrator`.

## Runtime boundary

- `desktop_ui/adapters/conversation_service_adapter.py` translates the frozen
  `ConversationApplicationService` result into UI view models.
- `scripts/desktop_app.py` composes the real MS10 backend.
- `scripts/desktop_demo.py` starts the same light UI with in-memory data.
- `requirements-ui.txt` adds PySide6 to the backend environment.

The UI calls only `ConversationApplicationService`. It does not import LangGraph
state, workflow plans, ToolRegistry internals, Supabase repositories, RAG
internals, or Automator UI logic.

## Install

```powershell
cd C:\GitHub\metastock-agent
pip install -r requirements-ui.txt
```

## Demo

```powershell
python -m scripts.desktop_demo
```

## Real backend

Set paths for the directories containing the local service entry points:

```powershell
$env:METASTOCK_RAG_REPO = "C:\GitHub\metastock-RAG-LLM"
$env:METASTOCK_AUTOMATOR_REPO = "C:\GitHub\metastock-automator\main"
python -m scripts.desktop_app
```

`METASTOCK_AUTOMATOR_REPO` must point to the directory containing
`automator_service.py`.

The launcher creates `QApplication` before constructing the Automator client so
Qt establishes the Windows GUI/OLE apartment first.
