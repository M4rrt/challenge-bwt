# 04 — Criar e listar conversas

**What to build:** An authenticated user can create a Conversation (1:1 or group) and list the conversations they belong to. Follows ADR-0002 (explicit, idempotent creation) and the `Conversation`/`ConversationParticipant` vocabulary in `CONTEXT.md`.

**Blocked by:** 03 (needs an authenticated user).

**Status:** done

- [x] `Conversation` + `ConversationParticipant` models + Alembic migration
- [x] `POST /conversations` — participant user IDs (+ required name for groups); idempotent for 1:1 (returns existing conversation if one already exists between the same two users)
- [x] `GET /conversations` — lists only the requesting user's conversations
- [x] Tests: create 1:1, create group, duplicate 1:1 creation returns the same conversation, a user cannot see conversations they're not part of

## Comments

Implemented TDD (red-green per cycle): models + migration `392b338ac5fb`, `app/services/conversation.py`, `app/routers/conversations.py`, `tests/test_conversations.py` (6 tests, all passing alongside the existing 6). Idempotency for 1:1 checks both membership and total participant count so a group containing the same two users isn't mistaken for their 1:1 (covered by `test_one_to_one_creation_ignores_group_with_same_two_members`).
