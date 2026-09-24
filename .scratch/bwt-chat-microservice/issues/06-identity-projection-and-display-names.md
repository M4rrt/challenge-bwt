# 06 — Identity projection and display names

**What to build:** The service knows a user's name and avatar without ever asking the monolith at request time. A profile row exists from the moment someone is added to a Chat, because the command that added them carried it, and an inbound event stream carries the rest of the lifecycle — creation, change, deactivation, anonymisation — so in practice the projection already knows any user before they join anything.

The rule that keeps this honest: no message table stores the sender's name, email or avatar, only their identifier. That is what makes an anonymisation in the monolith reach chat history without the service needing to know what data-protection law is. Denormalising the name "to save a join" breaks it silently.

**Blocked by:** 05.

**Status:** ready-for-human

- [x] A profile row carries Company, user kind, display name, avatar, source-updated-at and synced-at
- [x] Three inbound writes feed it: the identity in a composition command, an identity event, and a bulk load for initial population and rebuild
- [x] All three are idempotent, and last-writer-wins by source-updated-at, so an out-of-order event cannot resurrect a stale name
- [x] Identity events arrive on the internal ingress, at-least-once, and a redelivery writes nothing — by `source_updated_at` rather than by a table of seen event ids; see the note below
- [x] Message responses resolve the sender's display name from the projection at build time
- [x] No message table has a column holding a name, email or avatar
- [x] An anonymisation event reaches existing history — past messages stop showing the old name
- [x] Projection lag — the largest gap between source-updated-at and synced-at — is observable

## Comments

### The identity event carries no type

Creation, change, deactivation and anonymisation all arrive as the same write: a
snapshot of the identity plus `source_updated_at`. A projection stores what is
true now, and every response reads exactly that, so storing the verb would store
something nothing reads. It also keeps the data-protection policy — and its
wording — in the monolith: anonymising is the monolith sending the name it wants
shown, not this service deciding what "anonymised" looks like in Portuguese.

The wire shape ticket 05 fixed (`ParticipantIdentity`) was not touched. The event
stream is a new route, so nothing moved under the monolith.

### No table of seen event ids

The criterion asks for deduplication by event id. It was closed by argument
rather than by a table, because `source_updated_at` already settles it: a
redelivered event carries the timestamp it carried the first time, the comparison
in `apply_identities` is strict, and an equal timestamp loses. A replay writes
nothing — arriving once or ten times, in any order, interleaved with anything.
A table of seen ids would have been a second mechanism for the same property.

That argument has one load-bearing clause — *an equal timestamp loses* — and it
is tested: `test_replaying_an_event_writes_nothing_at_all` replays an identical
event and asserts the projection's lag does not move, which it would if the row
had been rewritten. Loosening the comparison to `<=` fails it.

`event_id` stays required on the wire. It is what makes a replay legible in a
log, and the moment this ingress grows work that is not idempotent by
construction — an outbox row on the way out, which is [15](15-outbound-push-events.md)
— the timestamp stops covering it and the table becomes load-bearing. It belongs
to that ticket.

One case neither mechanism covers: two genuinely distinct changes sharing one
`source_updated_at`. The second loses. If the monolith's identity clock turns out
to be coarse enough for that to happen, the fix is `<=` or a sequence number on
the event, not deduplication by id.

### The composition command is the weakest writer

`ParticipantIdentity` carries no `source_updated_at` and could not gain one
without moving the wire shape [05](05-composition-arrives-as-a-command.md) fixed.
So that write creates a row when nobody has said anything about the user and
never overwrites what something dated already said — which is last-writer-wins
applied uniformly, with an undated identity treated as the oldest thing there is.

Two composition paths that used to return without committing now commit: the
reuse of an existing 1:1, and an add-participant command that changes nothing
about the Chat. Both write profiles now, and a session closed with work open
rolls back — so returning without committing would have discarded the identities
exactly on the redelivery that carried them again.

### Projection lag lives in its own module

`app/services/projection_health.py` holds one function. It reads every Company's
rows, because the operator asking has no token and a lag computed per Company
would hide the stalled one behind the healthy ones — the same shape as the
drain's `oldest_unpublished_age`. The exemption in
`tests/test_company_isolation.py` is per entity but can only be declared per
file, so keeping the function separate is what lets `profiles_by_user_id` — a
read genuinely on behalf of a user — stay guarded in `app/services/identity.py`.

### Where the code and `spec.md` disagree

`spec.md` says the projection table is "keyed by user identifier". It is keyed by
`(company_id, user_id)` instead. The same user id can exist in two Companies —
which is why every fan-out address already carries the Company — and two
Companies may describe the same person differently, so a single key by user would
let one Company's name sign a message in another's Chat. That is the failure
`test_a_display_name_from_another_company_is_never_resolved` pins down, and it is
worse to find than a leaked row, because the message, the Chat and the
Participants are all correctly isolated and only the name is wrong. `spec.md` is
the line that should move.

### The realtime frame keeps the name it was sent with

`_persist_and_announce` resolves the sender's name and writes the finished
payload into the outbox row, so a live frame carries the name that was true when
the message was sent. An anonymisation landing in the seconds between the write
and the drain publishing it reaches history immediately but not that one frame;
any client re-reading the thread gets the current name. This is the one copy of a
display name outside `user_profiles`, and it sits outside
`test_no_message_table_stores_a_name_an_email_or_an_avatar`, which only scans
tables named for messages. It is a point-in-time delivery record rather than
storage — ticket 21 prunes it — so it is recorded here rather than changed.

### Transaction ownership is asymmetric on purpose

`apply_identities` commits; `remember_identities` deliberately does not, because
its write has to land in the same transaction as the composition that carried it.
The cost is that both composition paths which return early now have to commit,
and a future early return in `create_chat` or `add_participant` would silently
drop the profiles the command carried. No test guards that shape today.

### Left for other tickets

No index on `display_name`. Search by participant name is
[10](10-chat-list-with-name-search.md), and it will likely want a trigram index
rather than a b-tree, since the search is by substring.

`projection_lag` is a function, not an endpoint, exactly as
`oldest_unpublished_age` is. Turning both into something monitored is
[18](18-operational-surface.md).

Nothing reads `user_profiles.user_kind` yet. The visibility rule takes the
reader's kind from the token, never from this column, so it denies nobody
anything today — the ticket asks the row to carry it, and a chat list that shows
who it is talking to ([10](10-chat-list-with-name-search.md)) and supervised
reading ([13](13-supervisor-reading.md)) are what plausibly read it first.

Found while working here and left alone as out of scope: `backend/README.md`'s
"## Autenticação" section still describes an opaque refresh token, SHA-256
hashing and a rotation policy. [01](01-chat-token-replaces-own-login.md) deleted
all of it; `app/routers/auth.py` is `/auth/me` and nothing else.
