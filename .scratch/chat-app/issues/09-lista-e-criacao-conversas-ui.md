# 09 — Lista e criação de conversas (UI)

**What to build:** A logged-in user sees their conversations and can start a new one (1:1 or group), consuming ticket 04's API.

**Blocked by:** 08, 04, 15.

**Status:** done

- [x] Conversation list screen, fetched via TanStack Query, showing only the user's own conversations
- [x] "New conversation" flow — pick participant(s), name required for groups
- [x] Selecting an existing 1:1 contact reuses the existing conversation (reflects the idempotent backend behavior)
- [x] Tests: list renders the user's conversations, creating a 1:1 with an existing contact doesn't duplicate it in the UI

## Comments

Blocked-by amended to include ticket 15: the participant picker needed `GET /users` (id + username) to resolve who's who, since `GET/POST /conversations` only ever deals in raw participant UUIDs.

Implemented TDD (red-green per cycle):

- `lib/api.ts` — `getMe`, `listUsers`, `listConversations`, `createConversation`, plus the `CurrentUser`/`UserSummary`/`Conversation` types. `register()` also updated to send the now-required `username` (ticket 15 fallout, `Register.tsx` gained a matching field — separate commit).
- `routes/Conversas.tsx` — three TanStack Query reads (`me`, `users`, `conversations`) plus a `createConversation` mutation. A conversation's label is its `name` for groups, or the other participant's username (resolved via the `users` list) for a 1:1, falling back to "Conversa" if not yet resolved.
- Participant picker: checkboxes over every other registered user; the group-name field only renders (and is `required`) once more than one participant is selected, mirroring the backend's `len(participant_ids) > 2` (self + 2 others) threshold — selecting exactly one other user stays a 1:1, no name needed.
- Idempotency in the UI: on a successful create, the mutation invalidates the `conversations` query instead of appending the response locally — since the backend returns the *existing* conversation for a repeat 1:1, refetching from the server is what keeps the list from showing a duplicate, rather than any client-side ID-dedup logic.
- Tests (`Conversas.test.tsx`, 3 cases): list renders both a group (by name) and a 1:1 (by resolved username); submitting a 2-participant selection without a group name is blocked (native `required` validation) and only proceeds once one is typed; re-picking an existing 1:1 contact calls `createConversation`, gets the same conversation back, and the contact's name still appears exactly once in the list.
- Full suite green: 23 frontend tests (7 files), 30 backend tests; `tsc -b` and `oxlint` clean (one pre-existing, unrelated `AuthContext.tsx` warning).
