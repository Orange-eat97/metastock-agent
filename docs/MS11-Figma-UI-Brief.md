# MS11 approved UI brief

The approved source is the supplied **Chatbox with Approval Buttons** page.

## Layout

1. A 224 px conversation-history timeline.
2. A single chat panel with header, message stream, inline artifact cards, status,
   and composer.
3. No permanent detail panel.

## Visual rules

- Light colors only.
- White cards and background.
- Neutral gray borders and muted surfaces.
- Rounded panels, bubbles, cards, and composer.
- Compact Segoe UI typography.
- Dark user bubbles; muted assistant bubbles.
- No additional dashboard chrome.

## Functional mapping

- History entries open durable backend conversations.
- `+` creates a conversation.
- Ellipsis menus expose Rename, Clear, and Delete.
- Explorer and result content appears inline only when returned for the user's
  current query.
- Approval buttons remain non-functional placeholders.
- Backend IDs are stored internally and hidden by default.
