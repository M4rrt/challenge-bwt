# 04 — Criar e listar conversas

**What to build:** An authenticated user can create a Conversation (1:1 or group) and list the conversations they belong to. Follows ADR-0002 (explicit, idempotent creation) and the `Conversation`/`ConversationParticipant` vocabulary in `CONTEXT.md`.

**Blocked by:** 03 (needs an authenticated user).

**Status:** ready-for-agent

- [ ] `Conversation` + `ConversationParticipant` models + Alembic migration
- [ ] `POST /conversations` — participant user IDs (+ required name for groups); idempotent for 1:1 (returns existing conversation if one already exists between the same two users)
- [ ] `GET /conversations` — lists only the requesting user's conversations
- [ ] Tests: create 1:1, create group, duplicate 1:1 creation returns the same conversation, a user cannot see conversations they're not part of
