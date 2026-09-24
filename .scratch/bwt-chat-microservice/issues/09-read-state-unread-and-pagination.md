# 09 — Read state, unread counts and cursor pagination

**What to build:** A Participant can find where they left off. Each Chat reports what they have not read, marking as read moves a per-Participant watermark, and history pages back stably no matter how much arrives while they scroll.

Pagination is a cursor over creation time and identifier, never an offset — an offset shifts under new arrivals, which is the one thing a chat guarantees will happen. The read timestamp is clamped to now on write, because without the clamp a future date on a client's clock marks as read a message that has not arrived yet.

**Blocked by:** 03.

**Status:** ready-for-human

- [x] Message ordering has a stable tiebreaker beyond creation time
- [x] History pages by cursor; paging back while new messages arrive neither skips nor repeats a message
- [x] A Participant's read state is a per-Chat watermark carrying the timestamp and the message it stopped at
- [x] Marking as read is clamped to now — a future timestamp cannot mark an unarrived message as read
- [x] Each Chat reports the caller's unread count
- [x] Read state and unread counts respect visibility: a Staff-only Message never counts for an end client

## Comments

**Implemented.** Backend only — the interface follows in ticket 17.

Three contract choices the ticket left open, settled with the user before the
first test:

- `GET /chats/{id}/messages` answers with `{"messages": [...], "next_cursor": ...}`
  rather than a bare array. A cursor needs somewhere to live, and in the body it
  is part of the answer: `next_cursor: null` is the only thing that says "you
  have reached the beginning". This breaks the legacy frontend's `Message[]`
  parse, which tickets 16-18 replace.
- Marking as read carries the caller's own `read_at` plus an optional
  `message_id`. Deriving the watermark from the named message's server-issued
  `created_at` would have been unspoofable — and would have made the clamp this
  ticket asks for unreachable, since a server timestamp is never in the future.
- The watermark only moves forward. Not in the checklist, but two clients on one
  account otherwise fight over the count.

Beyond the checklist, three things the work turned up:

- `ix_messages_chat_id_created_at_id` (migration `d8f1a5c37b92`). Without an
  index on the pair the cursor walks, the database sorts the whole Chat to
  return a page — worst on exactly the long threads that made paging necessary.
  It closes the "índice de `messages` favorece a query errada" item in the
  backend README's technical debt.
- `mark_read` runs the named `message_id` through `visible_to`, the same filter
  every read uses. Unchecked, the endpoint is an oracle: an end client walks
  identifiers, sees which are accepted, and learns which Staff-only Messages
  exist without being shown one.
- A `read_at` with no timezone reached a comparison against an aware `now` and
  failed as a 500. It is refused at the schema with 422.

No new columns: `last_read_at` and `last_read_message_id` were added ahead of
time by `c9b2f4d7e130`, which said so.

**Left alone deliberately.** `alembic check` fails on this branch — four items
(the `chat_type`, `message_visibility` and `participant_role` check constraints,
and `ix_outbox_pending`) are in migrations but not in model metadata. Verified
against the pristine tree: it fails identically there, so the drift predates
this work and fixing it is not ticket 09. The Insomnia collections under
`backend/insomnia/` are also stale from tickets 01 and 05 — they still call
`/auth/register` and `POST /chats` — and were not touched here.

### From the two-axis review

Both axes ran against the branch. Three findings were real and are fixed:

- **The watermark was write-only.** It came back only on the response to the
  `POST /read` that moved it, so a client reconnecting — or a second device —
  could see *how much* was unread but not *where it stopped*, which is the
  ticket's opening sentence. `GET /chats` now carries `last_read_at` and
  `last_read_message_id` beside `unread_count`.
- **A timestamp-only mark erased the anchor.** `message_id` is optional, and its
  absence was written through, so a client with only a clock would wipe the
  position an earlier mark established. The anchor is now kept when none is
  named.
- **The unread aggregate had no boundary test.** `unread_counts` is built over
  `Participant`, so only that side is scoped by `scope.select`; `Message` enters
  by `outerjoin` and is scoped by hand, which the AST guard cannot see.
  `test_the_unread_count_does_not_cross_company` now asserts it from the edge,
  and the README's isolation section says why a join side needs one.

Three were noted and deliberately not acted on:

- **A same-instant mark naming a different message leaves the anchor alone.**
  The rule is that the anchor follows the timestamp; with no new instant there
  is nothing new to anchor to. Narrow — `created_at` is `clock_timestamp()` at
  microsecond resolution — and the alternative is comparing positions in the
  total order on every mark.
- **`message_id` is not required to sit at or below `read_at`.** A caller can
  store a self-contradictory watermark. No spec line forbids it and nothing
  reads the pair as a pair.
- **Marking as read enqueues nothing.** A second device's chat list keeps the
  stale `unread_count` until something else announces the Chat. That is ticket
  11's work: the spec has the WebSocket protocol gaining a named *mark read*
  frame, and adding an outbox address for it here would be building half of it
  in the wrong ticket.

The reviews also flagged the clamp and the cursor each being tested twice
against `CLAUDE.md`'s "Test once". Kept: the spec asks for exactly that —
"Domain rules that are pure — the Staff-only Message predicate, cursor encoding,
the read-timestamp clamp — get direct unit tests **as well as** an end-to-end
test through seam 1."
