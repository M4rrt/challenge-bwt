# 17 — Lista de conversas não atualiza em tempo real

**What to build:** A participant sees a new conversation appear in their sidebar as soon as someone else starts it with them, and gets some signal when a message arrives in a conversation they're not currently viewing — today, neither happens without a manual page reload.

**Blocked by:** none (builds on 06, 09, 10, all done).

**Status:** needs-triage — the problem is fully reproducible, but the fix needs a design decision (see below) before it's ready-for-agent.

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

- [ ] Decide push vs. polling for the conversation list (see above)
- [ ] Implement: new conversation created by another user appears in your sidebar without a reload
- [ ] Implement: a message arriving in a conversation you have but aren't actively viewing surfaces in the sidebar (at minimum, the list stays accurate; a visual "new activity" indicator is a nice-to-have, not required)
- [ ] Tests: user B's sidebar reflects a conversation user A just created with them, without B reloading
