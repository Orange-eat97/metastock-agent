# MS11 / frozen MS10 compliance

## Backend boundary

- [x] `ConversationApplicationService` is the sole production chat portal.
- [x] Conversation CRUD maps to public application-service methods.
- [x] Turns use a fresh `client_turn_id`.
- [x] Multi-step outcomes are reconstructed from persisted tool-call records.
- [x] Synchronous turns execute on a `QThread`.
- [x] The frontend does not select actions, tools, or workflows.

## Approved UI behavior

- [x] The supplied light, simplistic chatbox style is retained.
- [x] Conversation history replaces the glossary timeline.
- [x] Explorer, result, and RAG-log cards are inline only on relevant turns.
- [x] Approval buttons are disabled visual placeholders.
- [x] New, Rename, Clear, and Delete remain available through subtle controls.
- [x] Conversation, Explorer, result, service-log, stream, and tool-call IDs stay
      hidden from normal UI text.
- [x] CSV filenames do not contain result UUIDs.
- [x] Diagnostics filter ID and UUID fields.

## Deferred

- [ ] Functional approval persistence or enforcement.
- [ ] Token streaming.
- [ ] Backend-published step progress.
- [ ] Cancellation of a running turn.
- [ ] Developer-only audit/ID viewer.
