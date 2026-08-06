# 05 — Enviar e buscar mensagens

**What to build:** A participant can send a message into a Conversation and fetch its message backlog. This is the highest-priority test surface from the design session — the isolation guarantee ("a user only sees conversations/messages they participate in") is the core thing being graded.

**Blocked by:** 04.

**Status:** done

- [x] `Message` model (`sender_id` nullable, `sender_type`, `source_label` for future webhook use per ADR — see ticket 07) + Alembic migration
- [x] `POST /conversations/{id}/messages` — persists a message; rejects if sender isn't a participant
- [x] `GET /conversations/{id}/messages` — backlog fetch; rejects if requester isn't a participant
- [x] Tests: participant can send/fetch, non-participant gets rejected on both send and fetch (the isolation test), message ordering is correct

## Comments

Implemented TDD (red-green per cycle): `Message` model + migration `086712edec77`, `app/services/message.py`, `app/routers/messages.py`, `tests/test_messages.py` (8 tests: 4 service-level unit tests against `db_session` directly, 4 HTTP tests via the `client` fixture — all passing alongside the existing 16).

The membership check (`_assert_participant`) is shared by `send_message` and `list_messages` and raises a single `ConversationNotFoundError`, mapped to 404 for both a missing conversation and a non-participant — see `docs/decisions.md` for why 403 was rejected (it would leak conversation existence to unauthorized users). `sender_type="user"` and `source_label=None` are hardcoded for this ticket; ticket 07's webhook path will set `sender_type="external"` and populate `source_label` using this same `Message` model and persistence path.
