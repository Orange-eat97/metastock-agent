# Desktop UI package

`desktop_ui` is the light PySide6 frontend for `metastock-agent`.

```text
PySide6 widgets
→ QThread worker
→ Ms10ConversationAdapter
→ ConversationApplicationService
```

The supplied chatbox page is preserved as a two-panel design:

- conversation timeline on the left;
- chat and query-specific inline cards on the right.

The frontend does not choose tools, compile workflows, or manage approval state.
Approval controls are disabled visual placeholders. Internal UUIDs remain hidden.

Run the demo:

```powershell
python -m scripts.desktop_demo
```

Run against MS10:

```powershell
python -m scripts.desktop_app
```
