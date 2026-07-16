# MS11 light chatbox mapping

This overlay adapts the supplied **Chatbox with Approval Buttons** page to the
`metastock-agent` PySide6 application without changing its visual direction.

## Preserved visual language

- light background and white cards;
- narrow timeline-style left panel;
- rounded 12 px outer panels;
- small neutral typography;
- muted assistant bubbles and dark user bubbles;
- compact rounded composer and send button;
- simple bordered approval cards;
- no permanent third detail panel.

## MetaStock mappings

| Supplied page | MetaStock Agent |
|---|---|
| Glossary timeline | Durable conversation history |
| Active glossary definition | Selected conversation timestamp |
| Assistant chat | `ConversationApplicationService` turns |
| Approval card | Disabled visual placeholder only |
| Chat response attachments | Explorer, result, RAG-log, clarification, or blocked/error cards |

Explorer formulas and result tables are rendered inline only on assistant turns
that returned those artifacts. Active Explorer/result/log IDs remain in view
models for backend calls but are not rendered in normal UI text, tooltips,
filenames, or diagnostics.

Conversation management remains available through the subtle `+` button and the
ellipsis menu on each history entry: Rename, Clear messages, and Delete.
