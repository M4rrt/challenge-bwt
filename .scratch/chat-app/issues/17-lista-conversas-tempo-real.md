# 17 — Lista de conversas não atualiza em tempo real

**What to build:** A participant sees a new conversation appear in their sidebar as soon as someone else starts it with them, and gets some signal when a message arrives in a conversation they're not currently viewing — today, neither happens without a manual page reload.

**Blocked by:** none (builds on 06, 09, 10, all done).

**Status:** done

## Repro

User A creates a conversation with user B and sends a message. User B, logged in with the sidebar open, sees nothing — the new conversation doesn't appear in their list until they reload or independently start a conversation back with A.

## Root cause

- `Sidebar`'s `['conversations']` query only refetches on initial mount and on the *creator's own* `createConversation` mutation (`onSuccess: invalidateQueries(['conversations'])`, `frontend/src/routes/Sidebar.tsx`). Nothing tells the *other* participant's session to refetch.
- The real-time path that does exist is scoped per already-open conversation: `useConversationSocket` (`frontend/src/lib/useConversationSocket.ts`) connects to `GET /websocket/conversations/{id}` only while that specific conversation's screen (`Conversa.tsx`) is mounted. It can't surface a conversation the user isn't currently viewing.
- Backend-side, `app/services/realtime.py`'s pub/sub is also keyed per-conversation (`conversation:{id}` channel via `ConnectionManager`) — there's no per-user channel a client could subscribe to for "conversations I'm a participant in changed."

Note: this is distinct from the unread-count/read-receipt gap already logged in `docs/decisions.md`'s Deferred section (no per-message read state) — that's about *within* a conversation already visible in the list. This ticket is about the conversation not showing up in the list at all.

## Open design question (resolve before implementation)

Two viable approaches, differing in effort and how well they match the project's "real-time" framing:
1. **Proper push**: a per-user WS channel (or subscribe the sidebar to every conversation the user is a participant in) so new conversations and cross-conversation message activity arrive live, no polling. More work, consistent with how message delivery already works.
2. **Simple polling refresh**: give the `['conversations']` query a `refetchInterval` (e.g. every few seconds) so the sidebar self-heals within a short window without a reload. Much less work, but is a step down from the real-time bar the rest of the app holds itself to, and only ever "eventually" surfaces the new conversation rather than immediately.

- [x] Decide push vs. polling for the conversation list (see above)
- [x] Implement: new conversation created by another user appears in your sidebar without a reload
- [x] Implement: a message arriving in a conversation you have but aren't actively viewing shows a visual "new activity" indicator in the sidebar (promoted from nice-to-have to required — see Design decision below)
- [x] Tests: user B's sidebar reflects a conversation user A just created with them, without B reloading
- [x] Tests: user B's sidebar shows an activity indicator for a conversation that received a message while B wasn't viewing it, and the indicator clears once B opens that conversation

## Design decision (resolved)

**Push, not polling** — a per-user WS channel, consistent with how message delivery already works (ADR-0001/0003).

Scope was expanded during design: the "visual new-activity indicator" is promoted from nice-to-have to **required** for this ticket, since `ConversationRead` currently has no message-derived state at all (no preview, no ordering, no unread flag) — meaning the bare-minimum "list stays accurate" bullet from the original spec was otherwise satisfied trivially by conversation-created alone, with nothing left for "message arrived" to actually do.

### Backend

1. `ConnectionManager` (`app/services/realtime.py`) gains a second registry, `dict[uuid.UUID, set[WebSocket]]` keyed by `user_id`, with `connect_user`/`disconnect_user`/`connections_for_user` mirroring the existing per-conversation methods.
2. New endpoint `GET /websocket/users/me` in `app/routers/websocket.py`, same `?token=` auth pattern as the existing conversation endpoint. Registers the connection in the new per-user registry (a user may have multiple simultaneous connections, e.g. multiple tabs — same `set` shape already supports this).
3. `run_subscriber` extends `psubscribe` to cover both `conversation:*` and `user:*`; routes each incoming event to the matching registry by channel prefix. No DB access inside the subscriber — it only forwards, keeping the existing publish/forward separation intact.
4. New shared helper (e.g. `notify_participants(db, conversation) -> None` in `app/services/realtime.py`) looks up a conversation's participants and publishes the same payload — `ConversationRead` plus a new `last_message_at` field — to each participant's `user:{id}` channel. No `type` discriminator: the frontend reacts identically to any event on this channel, so the payload doesn't need one.
5. `last_message_at` is **computed at read time** (subquery/join `MAX(Message.created_at)` per conversation in `list_conversations`), not a denormalized column — avoids a migration and avoids a second place that could drift out of sync with the `Message` table.
6. `create_conversation` (`app/services/conversation.py`) calls `notify_participants` after commit, notifying **all** participants including the creator (redundant invalidate on the creator's own tab is harmless — no special-casing).
7. `_persist_and_publish` (`app/services/message.py`, shared by both normal send and the ticket 07 webhook path) also calls `notify_participants` after commit — covers both message sources automatically, no separate webhook-specific wiring.
8. `GET /conversations` includes `last_message_at` on every item.

### Frontend

9. New hook `useUserSocket` (same reconnect shape as `useConversationSocket`), mounted in `Sidebar.tsx` (the one component mounted for the whole `/conversas` session regardless of which conversation, if any, is open). On any message: `queryClient.invalidateQueries({ queryKey: ['conversations'] })`.
10. Activity cursor stored in `localStorage`, key `chat-app:lastSeen:{userId}:{conversationId}` (namespaced by user id to avoid leaking "already seen" state between different users sharing a browser). Value is the conversation's server-side `last_message_at` at the time it was last seen — not the client clock, to avoid clock-skew drift between the two sides of the comparison.
11. Cursor is written on conversation open (mount) and again on close (the same `useEffect` cleanup pattern `useConversationSocket` already uses) — not on every incoming message. The currently-open conversation never shows the indicator regardless of timestamp (suppressed by id check), so there's no correctness need to update the cursor mid-view; deferring the write to open+close keeps it to two `localStorage` writes per visit instead of one per message.
12. Sidebar never shows the activity indicator for the conversation matching the current route (`conversation.id === activeConversationId`), independent of timestamps.
13. Cold start: a conversation with no cursor recorded yet is treated as **already seen**, not unseen — avoids a mass false-positive of indicators lighting up for conversations users already read, the first time everyone logs in after this ships. The indicator only starts meaning something for messages that arrive after this deploys.

## Post-verification fix: stale indicator on the conversation just left

Found during manual verification: a message arriving in the currently-open conversation, followed by navigating to a different one, left a stale activity dot on the conversation just left.

Root cause: `Sidebar` computes the dot from the `localStorage` cursor synchronously during render, but the cursor was only corrected by `Conversa`'s cleanup `useEffect`, which runs *after* the route-change render commits. Since a `localStorage` write doesn't trigger a React re-render, `Sidebar`'s stale (pre-correction) render was the last one ever painted for that conversation, until some unrelated event re-rendered it.

14. `Sidebar.tsx` gains `markCurrentConversationSeen`, called via `onClick` on each conversation's `ListItemButton`. It writes the currently-open conversation's cursor (from `conversationsQuery.data`) synchronously, before `react-router`'s `Link` navigates — so the next render already has the corrected cursor instead of racing an effect.
15. Regression test in `frontend/src/routes/ConversasLayout.test.tsx`: `'does not show a stale new-activity indicator on the conversation just left, after a live message arrived while it was open'` — mounts `Sidebar` and `Conversa` together (the real integration point), pushes a live message while the conversation is open, then asserts the dot doesn't appear after navigating away.
