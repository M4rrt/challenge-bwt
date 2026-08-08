# 23 — Fix: wrong participant name shows on both sides of a conversation

**What to build:** Fix a bug where, when creating a 1:1 conversation, the displayed name is the same on both sides (creator and invitee) instead of each user seeing the other participant's name. Root cause: a race condition in `conversationLabel` between `meQuery` and `conversationsQuery` (`currentUserId` still `undefined` degrades `.find` to "first participant"), amplified by non-deterministic ordering of `participant_user_ids` on the backend (Python set with no `order_by`).

**Blocked by:** None — isolated bug fix, can start immediately.

**Status:** done

- [x] `conversationLabel` returns a fallback ("Nova Conversa") instead of degrading to the first participant when `currentUserId` is `undefined` (`frontend/src/lib/conversationLabel.ts`)
- [x] Test covering `currentUserId === undefined` in `frontend/src/lib/conversationLabel.test.ts`, written before the implementation (red confirmed, then green)
- [x] `participants` relationship in `backend/app/models/conversation.py` gets `order_by` (`ConversationParticipant.user_id`)
- [x] Test covering deterministic ordering in `backend/tests/test_conversation_model.py` (mapper-level, not integration — see Comments), written before the implementation (red confirmed, then green)
- [x] Existing suites (`Sidebar.test.tsx`, `Conversa.test.tsx`, `test_conversations.py`) keep passing unchanged

## Comments

Implemented on the `worktree-ticket-23-fix-conversation-label-race-condition` worktree.

**Fix 1 (frontend, root cause) — done.** `conversationLabel.ts` got a guard: when `currentUserId` is `undefined` (the race window between `meQuery` and `conversationsQuery` before `/auth/me` resolves), it returns `'Nova Conversa'` instead of letting `.find((id) => id !== currentUserId)` degrade to "first participant in the array" — which is what caused the same name to show on both users' screens. TDD: new test in `conversationLabel.test.ts` (`does not fall back to the first participant when currentUserId is not yet known`) confirmed RED before the change (`expected 'beto' to be 'Nova Conversa'`), then GREEN. 29 frontend tests passing (`conversationLabel.test.ts`, `Sidebar.test.tsx`, `Conversa.test.tsx`).

**Fix 2 (backend, amplifier) — deferred, not implemented.** The original hypothesis was that `participant_ids` (a Python `set` with no `order_by` on the relationship) made `participant_user_ids` non-deterministic, amplifying the bug. While writing the ordering tests (`test_create_conversation_returns_participants_sorted_by_user_id`, `test_list_conversations_returns_participants_sorted_by_user_id`) to confirm RED before implementing, we discovered they **always pass even without the fix**: the `conversation_participants` table has a composite unique index `(conversation_id, user_id)` (via `UniqueConstraint`), and Postgres' planner uses that index for the lookup by `conversation_id`, returning rows already ordered by `user_id` as a side effect — confirmed via `\d conversation_participants` and via 8 consecutive test runs, all green. Verified in isolation in Python that a `set` of UUIDs by itself is *not* ordered (~50/50 per run), so the correct order observed is accidental (query-plan behavior, not an SQL/SQLAlchemy guarantee).

Without a reproducible RED test in this environment, and since the bug reported by the user is fully explained by Fix 1, it was initially decided (with the user) not to implement `order_by` now — to be reopened as a separate ticket if the ordering behavior turns out to be non-deterministic in practice (e.g. a query-plan change under larger data volume).

**Fix 2 (backend) — revisited and implemented.** The user asked to apply `order_by` anyway, as a safeguard against the current ordering being an accidental side effect of Postgres' query plan (composite unique index `(conversation_id, user_id)`) rather than a guarantee. Since the integration tests via `client` still don't reproduce RED (same cause: the planner already delivers ordered rows), the test was written at a different level — `backend/tests/test_conversation_model.py::test_participants_relationship_orders_by_user_id` inspects the SQLAlchemy mapper configuration directly (`sa.inspect(Conversation).relationships["participants"].order_by`), no database needed. RED confirmed (`order_by` was `False`), then GREEN after adding `order_by="ConversationParticipant.user_id"` to the relationship in `backend/app/models/conversation.py`. Full backend suite: 47/47 passing, no regressions.
