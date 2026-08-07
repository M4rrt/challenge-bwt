# 10 — Tela de chat

**What to build:** Opening a conversation shows its message backlog and new messages appear live, without a page refresh — the end-to-end demoable proof of the mandatory real-time requirement.

**Blocked by:** 09, 06.

**Status:** done

- [x] On open, fetch message backlog via ticket 05's REST endpoint (TanStack Query)
- [x] Open a WebSocket connection (ticket 06) for the active conversation; incoming messages pushed into the same TanStack Query cache as the backlog (per `docs/decisions.md`'s frontend-tooling decision)
- [x] Send-message input posts via REST and/or WS per the backend's chosen path
- [x] Tests: backlog renders on open, a message sent from another session appears live without a manual refresh

## Comments

Requirements were pinned down via a `/grill-me` session before implementation — the resulting screen is an MUI-based split layout, not a separate route per conversation: `/conversas` is a layout route with a sidebar (conversation list + the existing "Nova conversa" flow) on the right and a center chat panel filled via a nested `/conversas/:conversationId` route. Index route (no id) shows an empty-state placeholder — no auto-select.

Implemented TDD (red-green per cycle), seams agreed up front:

- `lib/api.ts` — `Message` interface, `listMessages`, `sendMessage`, `toWsUrl` (scheme-swap helper for the WS URL, derived from the same `VITE_API_URL` rather than a second env var). `API_URL` also exported for the WS hook to reuse.
- `lib/messageGrouping.ts` — pure `groupMessages(messages, usernameById)`, unit-tested directly: consecutive same-`sender_id` messages collapse into one group (name + `HH:mm` timestamp shown once, from the group's first message); a different `sender_id` starts a new group; `sender_id: null` falls back to `source_label ?? 'Bot'` — written ahead of ticket 07's webhook path landing, per explicit user request (see follow-up ticket 16). Grouping is purely by `sender_id`, no time-gap regrouping.
- `lib/useConversationSocket.ts` — one WS connection per active conversation (opens on mount/`:conversationId` change, closes on unmount/change), fixed-delay reconnect on an unexpected close, silent (no UI indicator), not reconnecting on a deliberate close. Not unit-tested directly (no seam agreed for it) — exercised transitively through `Conversa.test.tsx`'s mocked-`WebSocket` tests.
- `routes/Sidebar.tsx` — `Conversas.tsx`'s list+create-conversation logic, relocated and re-skinned in MUI (`Paper`/`List`/`ListItemButton`, participant picker via `Checkbox`+`FormControlLabel`), conversation items now `Link`-wrapped to `/conversas/:id` with active-item highlighting via `useParams`. `Conversas.tsx`/`Conversas.test.tsx` deleted; the 3 existing tests ported byte-for-byte into `Sidebar.test.tsx`, with one adjustment — `getByLabelText('Nome do grupo')` had to become a regex match, since MUI's required-field label renders the text as `"Nome do grupo *"` in the DOM.
- `routes/ConversasLayout.tsx` + `ConversaEmptyState.tsx` — the layout shell (sidebar + `Outlet`, spaced/rounded panels for the MSN look) and the no-conversation-selected placeholder.
- `routes/Conversa.tsx` — the chat screen. No optimistic send (waits for the REST response, then writes it into the `['messages', conversationId]` cache via an id-deduped `upsertMessage` helper — the same helper the WS `onMessage` callback calls, since the backend also echoes a sender's own message back over their own connection). Enter sends, Shift+Enter inserts a newline. Auto-scrolls to bottom on open and on new messages only if already scrolled to bottom; otherwise shows a "Novas mensagens ↓" pill that scrolls on click — this scroll logic is implemented but intentionally not unit-tested (jsdom has no real scroll geometry, agreed with the user to verify manually) — `Element.prototype.scrollIntoView` had to be stubbed in `test/setup.ts` since jsdom doesn't implement it at all, which was blocking the other seam tests too.
- `theme.ts` — small custom MUI `ThemeProvider` (primary color, `background.default`, `shape.borderRadius: 12`) wired at the `App.tsx` root, alongside the new nested route tree. New dependency (`@mui/material` + emotion) logged in `docs/decisions.md`'s frontend-tooling section.

Three confirmed seam tests in `Conversa.test.tsx`: backlog renders on open; a message pushed over a mocked WS (`.onmessage` fired manually) appears without a second `listMessages` call; a sent message only appears once the mocked `sendMessage` promise resolves (proves no optimistic add).

Full suite green: 36 frontend tests (10 files), `tsc -b` and `oxlint` clean (same one pre-existing, unrelated `AuthContext.tsx` warning noted in ticket 09).

Follow-up: ticket 16 tracks verifying the `source_label ?? 'Bot'` fallback against ticket 07's real webhook payload shape once that lands.
