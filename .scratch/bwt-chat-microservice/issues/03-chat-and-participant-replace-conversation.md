# 03 — Chat and Participant replace Conversation

**What to build:** The domain speaks the glossary in `CONTEXT.md`. A Chat is a container for messages between a set of Participants, typed `staff` or `client`; a 1:1 is a Chat with exactly two Participants, not a separate concept. A Participant carries the link between a user and a Chat, their read state, and the moment they left it if they did.

Public creation still exists at the end of this ticket — ticket 05 is what replaces it with the command from the monolith. Keeping it here is what lets this slice land green and demoable on its own.

**Blocked by:** 02.

**Status:** ready-for-human

- [x] Chat carries Company, type (`staff` | `client`), optional name and timestamps; the words Conversation, Room and Sala appear nowhere
- [x] Participant carries Chat, user identifier, Company, role, joined-at, left-at, last-read-at and last-read-message
- [x] A group Chat requires a name; a 1:1 does not
- [x] Opening a 1:1 that already exists returns the existing Chat rather than creating a second one
- [x] A Staff Chat containing an end client is rejected — the shape of the Chat is the service's own business to validate
- [x] A Participant who left stops appearing as a current Participant without their row being deleted
- [x] Cross-Company isolation tests extended to cover Chat and Participant

## Comments

### What landed

`Conversation` and `ConversationParticipant` became `Chat` and `Participant`, all the way down: tables, columns, HTTP routes (`/chats`, `/chats/{id}/messages`, `WS /websocket/chats/{id}`), the Redis channel (`chat:{id}`) and the error type (`ChatNotFoundError`). `tests/test_glossary.py` scans `app/` and `tests/` for the words `CONTEXT.md` lists under _Avoid_ and fails naming file and line, so the naming is a property of the code rather than a habit.

Three migrations, each a separate record: the rename (`a3f7c2e51b08`, in-place, nothing dropped), Chat type and Participant role (`b7e1d0c4a92f`), and Chat timestamps plus the Participant's departure and read state (`c9b2f4d7e130`).

`POST /chats` now carries the Chat's type and each Participant's kind:

```json
{ "type": "staff", "participants": [{ "user_id": "<uuid>", "user_kind": "staff" }], "name": null }
```

The caller is added from their own token's `user_kind`. Three refusals reach the router as subclasses of one `ChatShapeError`, so it does not enumerate them: a Staff Chat containing a client, a group without a name, and a *caller's* user kind outside `staff`/`client`. A named Participant's bad kind never gets that far — pydantic rejects it at the edge. Same `422`, different path.

### Decisions taken here

- **The create command carries participant kinds.** "A Staff Chat containing an end client is rejected" is unvalidatable otherwise — the service holds no user table, so the only way it can know a client from a staff member is for the command to say. This is the spec's composition-command shape arriving early, which makes ticket 05 a transport swap rather than a redesign.
- **Leaving is `left_at`, and there is one spelling of "current".** `STILL_IN_THE_CHAT` (`app/models/chat.py`) in queries, `Chat.current_participants` in Python. The relationship deliberately still loads everyone, because tickets 09 and 13 need to reach a departed Participant's row.
- **1:1 idempotency matches on type as well as on the pair.** Not in the checklist, but without it `POST /chats {"type": "client"}` could answer `201` with a Chat whose `type` is `staff` — a response to a question nobody asked.
- **Existing rows were truncated, not backfilled.** Same grounds `c1d4a7e90f32` gives: the service has never been in production and the rows are development fixtures. Nothing distinguished a Staff Chat from a Client Chat among them, and a guessed type is a validation rule quietly evaluated against a made-up input.
- **The chat list is ordered in the service, not the router.** Ordering by last activity is part of what a chat list is, so `list_chats` returns `list[ChatRead]` already sorted and the router is a pass-through. `ChatRead.of` is now the single constructor shared by the list, the create response and the live push over `/websocket/users/me` — built at each site, a field added to one would quietly disagree with the other two.
- **Enum columns are stored by value with a CHECK.** SQLAlchemy persists a Python enum by member *name*, so `ChatType.STAFF` was landing in the column as `STAFF` while every payload and migration said `staff`. Nothing reading through the mapper could see it; the CHECK constraint is what caught it. `tests/test_chat_model.py` guards it now.

### Left out, on purpose

- **The frontend still sends the old create payload.** The vocabulary pass covered `frontend/src`, but rewiring the client to the new contract is ticket 17's job, and the interface has been unable to reach this backend since ticket 01 removed `/auth/login`, `/auth/register` and `/users`. Same for `backend/insomnia/*.json`, whose request chains start with a register/login that no longer exists.
- **A Client Chat with no client in it is accepted.** The spec enumerates what the service validates — "that a Staff Chat contains no client, that a group has a name, that the 1:1 does not already exist" — and the mirror rule is not on that list. Worth a decision in ticket 04 or 05, since that is where `Chat.type` starts deciding visibility.
- **`Message.sender_type` is still a bare string.** `Chat.type` and `Participant.role` got real enums; `sender_type` keeps its `"user"`/`"external"` literals. Same concept, two treatments — left to ticket 08, which owns message send semantics.
- **`Chat.updated_at` never moves.** Nothing writes a Chat row after creation yet. The column is there because the spec says Chat carries timestamps; the first writer will be ticket 05.
- **`backend/README.md`'s "Autenticação" section is stale.** It still describes the refresh-token table ticket 01 deleted. Left for whoever closes that loop rather than folded in here.
- **ADR bodies were reworded, not rewritten.** `docs/adr/0002` was renamed to `0002-explicit-idempotent-chat-creation.md` and ADR-0011's "room" became "Chat". Only the vocabulary moved; no decision, context or date changed.
- **`alembic/versions/` keeps saying `conversations`.** A migration is a dated record, and rewriting the one that created the table would make `alembic upgrade` from an empty database build tables the later migrations cannot find. `test_glossary.py` excludes the directory and says why.
