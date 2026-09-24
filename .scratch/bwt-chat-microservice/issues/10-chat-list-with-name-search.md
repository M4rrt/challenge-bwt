# 10 — Chat list with search by participant name

**What to build:** A Company staff member finds a thread among hundreds by typing the name of the person they were talking to, and the filtered list pages exactly like the unfiltered one.

This is the ticket that proves the projection earns its place. The source module's filter joined on participant name, and you cannot paginate a list filtered by a column the database does not have — which is why profiles live in the chat's database at all, and why resolving a name is never a call.

The list does not load messages in bulk: each Chat's last message comes from one row per Chat, not from prefetching every collection.

**Blocked by:** 06, 09.

**Status:** ready-for-human

- [x] The Chat list is ordered by last activity and carries each Chat's last message and the caller's unread count
- [x] Each Chat's last message is fetched as one row per Chat rather than by prefetching whole message collections
- [x] The list filters by participant name, resolved against the projection with no outbound call
- [x] The filtered list pages by the same cursor contract as the unfiltered one
- [x] The name filter never matches, or reveals, a name from another Company
- [x] A Chat's last message respects visibility — an end client never sees a Staff-only Message as the list preview

## Comments

**Implemented.** Backend only — the interface follows in ticket 17.

Three contract choices the ticket left open, settled with the user before the
first test:

- `GET /chats` answers with `{"chats": [...], "next_cursor": ...}` rather than a
  bare array, which is ticket 09's `MessagePage` decision applied to the list:
  an array has nowhere to put a cursor, and `next_cursor: null` is the only
  thing that says "there are no more Chats" — a page that came back short does
  not say it, because a limit and a remainder can coincide. **This breaks the
  legacy frontend's `Chat[]` parse** (`frontend/src/lib/api.ts`), exactly as
  ticket 09 broke its `Message[]` parse. Tickets 16-18 replace that frontend.
- The name filter matches any *other* current Participant's `display_name` **or**
  the Chat's own name. The Chat's name is in because spec item 21 is the only
  reason a group carries one — it is what makes a five-person thread
  identifiable in a list, and a filter that saw only people would leave it
  unsearchable. The caller is out because they are a Participant of every Chat
  in their own list, so matching themselves would answer "find the person I was
  talking to" with the unfiltered list, which reads as the filter silently not
  working.
- Accents are folded on both sides, via the `unaccent` extension. Brazilian
  names carry them and the people searching often do not; matched exactly, the
  search box fails on the most common surnames in the Company's own country,
  and fails silently — an empty list reads as "no such thread".

Beyond the checklist, four things the work turned up:

- **The cursor pages over `(last activity, chat id)`, and last activity needed an
  instant for silence.** A Chat nobody has spoken in has no last message, and a
  null sorts wherever the plan puts it — a cursor over an order the plan chooses
  is a cursor that skips rows. It sorts at the Unix epoch instead, spelled once
  in SQL (`_last_activity`) and once in Python (`_activity_of`), which have to
  agree to the microsecond because the cursor encodes microseconds. The
  identifier is the tiebreaker, for the reason ticket 09 gave about messages:
  every silent Chat shares the epoch, so without it the order is partial and the
  page boundary serves a Chat twice or loses it.
- **The visibility rule gained a third SQL shape.** `visible_to` asks it of a
  Chat already loaded and `in_a_chat_the_reader_may_see_it_in` of a set of
  identifiers; neither works for a query that has not chosen its Chats yet,
  which is what ordering and paging by last activity requires. The new
  `_visible_in_the_joined_chat` reads the type off `Chat.type` in the FROM
  clause. All three derive their visibilities from `readable_visibilities`, so
  they differ in what they have to hand and never in what they mean — which is
  the whole guard against ADR-0008's defect returning.
- **`OLDEST_FIRST`/`NEWEST_FIRST` and `message_responses` moved down the import
  graph** — the first to `app/models/message.py`, the second to
  `app/services/identity.py`. `services/message.py` imports `services/chat.py`,
  so the chat list could not reach either where ticket 09 left them. Both are
  now single-spelled for the two readers rather than duplicated: the list
  previews the row the thread opens on because both take the same order, and a
  name in a preview is resolved by the same bulk helper the thread uses.
- **`ChatRead.last_message_at` is now derived from `last_message`, not passed
  beside it.** Taking both would let a caller hand over a timestamp belonging to
  a different message from the one it previews, and the two would then disagree
  in a response nothing else explains.

**Left alone deliberately.** The legacy frontend is not updated (above). The
search matches substrings and does not rank by relevance — `pg_trgm` is
installed and `similarity()` would fix it, but relevance is a second ordering
key and the cursor pages over the ordering key, so it is a pagination change
rather than a filter change and did not belong in the ticket that introduced
the cursor. Both are recorded in `docs/decisions.md` and the backend README's
technical-debt list, along with the list's own missing index: the order is an
expression over the lateral's output, not a column, so Postgres sorts the join
result.

`alembic check` is clean on this branch, including the new functional index —
the model declares it as well as the migration, which is the convention
`ix_messages_chat_id_created_at_id` set.

### From the two-axis review

Both axes ran against the branch. Three findings were real and are fixed:

- **The push path previews a message body now, and nothing tested it.** Giving
  the summary a `last_message` made `/websocket/users/me` a second way a
  Staff-only Message could reach an end client — the spec's rule is "never over
  the API, never in a count, never as a gap in pagination", and a push is
  outside that list only in the sense that nobody had written it down. The
  filter was already per role and correct;
  `test_the_pushed_summary_never_previews_a_staff_only_message` is what stops
  it silently ceasing to be. Removing the filter makes it fail, which is how it
  was checked.
- **The cursor page shape was written twice.** `list_chats` and `list_messages`
  each carried `limit + 1`, the slice, and the "is there more" comparison, with
  the argument for the extra row in both docstrings. It is `page_of` in
  `core/cursor.py` now — the repo's own line about the visibility rule, that a
  filter written twice is a filter updated once, applies to a page shape too.
  Building the cursor deliberately stayed out: where a page resumes from is the
  one part that genuinely differs.
- **`docs/decisions.md` still pointed `OLDEST_FIRST` at `app/services/message.py`.**
  This ticket moved it to `app/models/message.py` and updated the README but
  not the decisions log.

Smaller: `matching_the_search` became private like its siblings; a local
`Select` named `listed` no longer shares a word with the new test helper;
`search.strip()` is bound once; the single-element bulk call in
`enqueue_chat_summaries` is spelled the way `_announce` spells it; the epoch
argument is stated once at `_UNIX_EPOCH` instead of three times; the test
helpers take `str | int | None` rather than `object`; and the statement-count
test lost its `noqa` and its `db_session.bind.sync_engine` chain.

Four findings were noted and deliberately not acted on, all recorded in
`docs/decisions.md`:

- **The search only sees current Participants.** A 1:1 stops being findable by
  the other person's name once they leave, and a 1:1 has no name of its own.
  The review is right that this is in tension with "the person they *were*
  talking to". Kept because every other read means the same thing by
  "Participant" — `participant_user_ids` shows only current members, so
  matching a name the response does not carry would be a result nothing on it
  explains. It is a one-line change if you would rather have it the other way.
- **The statement-counting test reaches into the session**, which the spec's
  Testing Decisions ask tests not to do. Kept because the ticket makes the cost
  a requirement and no response distinguishes one query from thirty. It is the
  only test in the suite that does this.
- **`pg_trgm` is a second extension** beyond the `unaccent` that was agreed.
  It is what makes the filter indexable at all: `ILIKE '%...%'` has a leading
  wildcard, which is exactly what a btree cannot answer.
- **Only half the `OR` is indexed.** The Chat's own name is scanned. Bounded by
  the caller's own Chats rather than by the Company's profiles, which is why it
  was left.

The Company-isolation finding on the search path was already covered:
`test_the_filter_does_not_match_a_name_from_another_company` drives two search
*requests* from two Companies and asserts each sees only its own Chat, so a
second test would be the repeated assertion `CLAUDE.md` warns against.
