# 02 — Company boundary on every read

**What to build:** No read of any kind crosses a Company. A caller from one Company asking for another Company's Chat, message or Participant gets the same answer as a caller asking for something that does not exist.

In the source module this was a queryset invariant, and its docstring said isolation lived there and nowhere else precisely so no call site had to remember it. Leaving Django removed that floor — ADR-0007 names this the central risk of the architecture. So the replacement is structural, not a filter per call site: every readable entity gets its base query from one constructor that takes the caller's Company from the token, and a read path that does not go through it does not compile into existence.

**Blocked by:** 01.

**Status:** ready-for-human

- [x] Every persisted, readable row carries its Company
- [x] Each readable entity has exactly one base-query constructor, taking the Company from the caller's token
- [x] A cross-Company request for a Chat, a message list, or a Participant returns not-found, never forbidden — no response distinguishes "exists elsewhere" from "does not exist"
- [x] The isolation test covers every read path that exists at the end of this ticket, and adding a readable entity later means adding its isolation test
- [x] A caller whose token carries no Company reaches nothing

## Comments

**Where the boundary lives.** `backend/app/core/company_scope.py`. A readable row
carries its Company through the `CompanyScoped` mixin, and every read of one
starts from `CompanyScope.select`, which takes the Company from the caller's
token. `conversations`, `conversation_participants` and `messages` all carry it;
the migration deletes the rows that predate the column rather than inventing a
placeholder Company for them, because a placeholder files every old Chat under a
Company no token will ever name — data loss dressed up as data.

**"Does not compile into existence", in a language that cannot enforce it.**
Python has no way to make `select(Message)` fail to exist. What replaces the
compiler is a test in `tests/test_company_isolation.py`: it walks the AST of
every file under `app/` and fails, naming file and line, if anything outside the
scope module opens a read on a scoped entity — `select(E)`, `sa.select(E)`,
`session.get(E, ...)`/`get_one`, or `session.query(E)`. Everything else (a
relationship load, a refresh, a loader option) begins from a row a scoped query
already returned. The set of scoped entities comes from the SQLAlchemy mapper
registry rather than a hand-written list, so an entity added later is covered
the moment it is mapped. Each of those five shapes was checked by planting one
in a router and watching the test name it; `scope.select(E)` and
`CompanyScope.of(caller).select(E)` were checked to stay exempt.

That test found the two paths I had missed, `notify_participants` and
`get_last_message_at_by_conversation`, before any behavioural test did.

**Two limits it has, stated so the next person does not over-trust it.** It
recognises the sanctioned `scope.select(...)` by the receiver's *spelling*, not
its type, so a `CompanyScope` reached under a third name would be flagged; and
raw `text("SELECT ...")` is invisible to it.

**And one limit it had that mattered.** A fan-out is not a query, so the guard
is blind to it — and the Chat-list push over `/websocket/users/me` was keyed by
user id alone. The same person can hold a token in two Companies, so a Chat
summary published for one (its id, name, participants and `last_message_at`)
landed on the socket they had opened with the other's token. Spec item 11 says
"no read of any kind ... **or presence**", so this was in scope and it was a
real leak, found by the spec review rather than by me. The Redis channel is now
`user:{company_id}:{user_id}` and `ConnectionManager` keys its sockets by the
pair; `test_user_socket_does_not_receive_another_companys_chat` fails against
the old keying. **The general rule, now in `backend/README.md`: a path that
pushes rather than queries has to carry the Company in the channel key, because
no amount of scoping the read will scope the delivery.**

**Not-found, not forbidden, and provably so.** The filter lands in the `WHERE`
clause, so the cross-Company tests do not merely assert `404` — each asserts the
status *and body* are identical to the same request aimed at a UUID that never
existed. Nothing in the response distinguishes "exists elsewhere" from "does not
exist".

**There is no standalone Participant endpoint to test.** Participants are read
in two places, both covered: inside a Chat (so a Chat that is absent takes its
Participants with it) and by the 1:1 de-duplication lookup, which has its own
test — opening a 1:1 with the same person from a second Company now creates a
second Chat instead of handing back the first Company's.

**The webhook now names its Company.** `POST /webhook/messages` was the one
caller with no token and therefore no Company, and it read the Chat by primary
key. `WebhookMessageCreate` gains a required `company_id` and the Chat is read
inside it, so no unscoped read survives this ticket. **Breaking change** to the
webhook contract; `backend/README.md` is updated.

That closes the boundary but not the trust problem: the HMAC secret is still one
secret for every Company, so whoever holds it can sign a payload naming any
Company. Ticket [14](14-webhook-hardening.md) gives each Company a secret of its
own, which is what makes `company_id` in the payload worth anything.

**"A caller with no Company reaches nothing" was already true.** It comes from
ticket [01](01-chat-token-replaces-own-login.md): a token whose chat claims name
no Company never becomes a `Caller`, so the refusal is a `401` at the door
rather than an empty read behind it. The test is written anyway — the box asks
for the guarantee, not for new code.

**Test callers now share a Company by default.** `tests/chat_tokens.py` minted a
random Company per caller, which would have made every existing multi-caller
test fail for the right reason in the wrong place. Callers share
`DEFAULT_COMPANY_ID` unless a test names another one, so crossing the boundary
is always deliberate.

**From the review, also fixed.** The AST guard resolved `app/` relative to the
working directory, so running pytest from anywhere but `backend/` scanned zero
files and passed vacuously; it now resolves from `__file__` and asserts it
scanned something. A local in `_find_existing_one_to_one` had been renamed to
`exactly_these_members` — `CONTEXT.md` lists Member under `_Avoid_` for
Participant, and the name lied anyway, since it holds Chat ids. A dead
`select` import was left in `app/services/message.py`.

**The scope seam is uniform.** Routers no longer build a scope inline: it
arrives through `get_company_scope` (`app/core/security.py`), and every service
that needs a Company takes the `scope` as a parameter rather than deriving it
from the caller halfway down. `CompanyScope.of` is now called in exactly two
places, both entry points — that dependency, and the WebSocket handshake, which
has no dependency to hang off because its token is a query parameter.

**Not touched, and why.** `frontend/` and `backend/insomnia/` still call the
endpoints ticket 01 deleted, so both are already non-functional; the webhook
page and the webhook collection additionally now need `company_id` in their
payloads. Following ticket 01's precedent, they stay with
[16](16-interface-session-handoff.md) and [17](17-interface-chat-list-and-thread.md)
rather than being half-revived here. `backend/README.md`'s Autenticação section
still describes the refresh tokens ticket 01 removed — stale from that ticket,
left alone rather than fixed under this one.
