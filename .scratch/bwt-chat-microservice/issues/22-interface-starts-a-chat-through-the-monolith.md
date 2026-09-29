# 22 — The interface starts a Chat, through the monolith

**What to build:** A user of the interface can start a new Chat — pick who to talk to, name it if it becomes a group — and the interface asks the **monolith** to create it, never the service directly. This is the create-flow ticket 17 removed on purpose: composition is a monolith command ([ADR-0010](../../docs/adr/0010-no-request-depends-on-the-monolith.md), [05](05-composition-arrives-as-a-command.md)), so starting a Chat from the browser has to go through the same door.

**The monolith side of this does not exist yet.** There is no endpoint today, on the monolith, that a browser can call to start a Chat — `X-Acting-User`/`X-Acting-Company` composition headers and `/internal/chats` are service-side and were never meant to be public. This ticket cannot be finished — end to end, against the real monolith — until that endpoint ships in `brwinetours-backend-development`. What follows is built the way [16](16-interface-session-handoff.md) was: against an assumed shape, documented here, reconciled once the other side lands.

**Assumed contract** (mirrors `frontend/src/lib/monolith.ts`'s existing pattern):

- `POST {MONOLITH_URL}/chat/chats` `{ participant_ids: string[], name?: string }` → `{ chat_id: string }`, authenticated with the renewal credential from session handoff — as an `Authorization: Bearer` header, not the body field `issueChatToken` uses, because this endpoint's body is already fully specified above and has no room for a token. Same credential, different transport; reconcile against whatever the real endpoint expects.
- `GET {MONOLITH_URL}/chat/contacts?search=` → `Contact[]` where `Contact` is `{ id: string, display_name: string, avatar_url: string | null, kind: 'staff' | 'client' }`, same `Authorization: Bearer` auth. Assumed wholesale — the monolith side gives no shape for the contact/staff listing this ticket's picker needs, only the constraint that it must exist there and not on the service ([ADR-0010](../../docs/adr/0010-no-request-depends-on-the-monolith.md)).
- `participant_ids` identify users the way the monolith already does elsewhere in the product (staff directory / CRM contact picker) — the interface never resolves Company membership or contact status itself, same boundary as [05](05-composition-arrives-as-a-command.md). `participant_ids` never includes the caller; the monolith adds the acting user itself, mirroring the split the internal composition command already makes.
- `name` is required once more than one participant is picked (mirrors the `> 2` self-plus-others group threshold used elsewhere), optional for a 1:1.
- On success, the interface navigates to `/chats/{chat_id}`, the existing thread route from [17](17-interface-chat-list-and-thread.md).
- A monolith-side rejection (participant not in Company, not an active contact, etc.) surfaces as a visible error in the picker — the interface does not retry or guess a reason.

**Blocked by:** None in this tracker (05 and 17 are both done). Blocked in practice on the monolith exposing the endpoint above, or one shaped differently — reconcile before calling this done end to end.

**Status:** ready-for-human

- [x] A "start a Chat" entry point exists in the interface (`ChatsLayout` or equivalent), reachable from the chat list
- [x] Participant picker calls the monolith's own contact/staff listing — not `GET /users` on the service, which [17](17-interface-chat-list-and-thread.md) already established doesn't exist here
- [x] Picking more than one other participant requires a name before submitting; picking exactly one does not
- [x] Submitting calls `frontend/src/lib/monolith.ts`'s new `createChat`, and on success navigates to the new Chat's thread
- [x] A monolith-side rejection is shown to the user without crashing the picker or leaving it in a half-submitted state
- [x] Tests cover the picker's validation and the success/failure paths against a mocked monolith response — not a live one, since there is nothing live to call yet

## Comments

Opened after the user asked "which ticket lets us create a chat" and confirmed: yes, this belongs in the interface, requesting the monolith create it. Contract confirmed not to exist yet on the monolith side (not just undocumented here, as it was for 16) — flagged in [ADR-0010](../../docs/adr/0010-no-request-depends-on-the-monolith.md) as a known gap, not newly discovered.

**Implemented against the assumed contract above.** `frontend/src/lib/monolith.ts` gained `listContacts` and `createChat`; `frontend/src/lib/auth/AuthContext.tsx` now exposes `renewalToken` so components can authenticate those calls; the picker itself is `frontend/src/components/ChatsLayout/StartChat/StartChat.tsx`, reachable from a "+" entry point next to the chat count in `Sidebar`.

**Two assumptions this ticket's own contract left open, surfaced via `/code-review`'s spec axis and confirmed with the user before finishing:**

- **Auth transport for `createChat`/`listContacts`.** The bullet above originally said "authenticated the same way `issueChatToken` already is," which sends the renewal token as a body field (`{ renewal_token }`). `createChat`'s body is fully spoken for by `{ participant_ids, name? }`, so there's no room for a token field there — the renewal token travels as an `Authorization: Bearer` header on both new calls instead. Same credential, different transport. **Confirmed with the user:** keep the header, reconcile against whatever the real monolith endpoint expects once it exists.
- **The contact/staff listing's shape.** Unlike `createChat`, this ticket gave no assumed contract at all for the endpoint checklist item 2 requires — `GET /chat/contacts?search=` and the `Contact` shape above were invented to unblock the picker and are now written down here for the same reason `createChat`'s contract was: nothing to reconcile against until the monolith side exists.

Tests: `frontend/src/lib/monolith.test.ts` (both new functions' request shape and error mapping), `frontend/src/components/ChatsLayout/StartChat/StartChat.test.tsx` (list-populate, 1:1 success+navigate, >1-participant-no-name disables submit, group+name success, monolith rejection shown without resetting the selection), plus a Sidebar test for the entry point — all against a mocked monolith, per the checklist's own instruction that there's nothing live to call yet.
