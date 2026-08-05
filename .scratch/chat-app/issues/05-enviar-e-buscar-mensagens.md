# 05 — Enviar e buscar mensagens

**What to build:** A participant can send a message into a Conversation and fetch its message backlog. This is the highest-priority test surface from the design session — the isolation guarantee ("a user only sees conversations/messages they participate in") is the core thing being graded.

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] `Message` model (`sender_id` nullable, `sender_type`, `source_label` for future webhook use per ADR — see ticket 07) + Alembic migration
- [ ] `POST /conversations/{id}/messages` — persists a message; rejects if sender isn't a participant
- [ ] `GET /conversations/{id}/messages` — backlog fetch; rejects if requester isn't a participant
- [ ] Tests: participant can send/fetch, non-participant gets rejected on both send and fetch (the isolation test), message ordering is correct
