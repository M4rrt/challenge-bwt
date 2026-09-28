# 17 — Interface: chat list and thread

**What to build:** The Chat interface works against the new contract end to end: a list of Chats with each one's last message and unread count, a thread that pages back through history, composing and sending with the message appearing immediately, and a visible mark on a Staff-only Message both when writing one and when reading one — so nobody mistakes which thread they are writing into.

It also has to tell three closures apart, because treating them alike breaks in opposite directions: token expired means renew and reconnect, access revoked means leave the Chat and stop retrying, and a network failure means exponential backoff. Treating them all as failure turns every expiry into a growing wait; treating them all as expiry makes the client hammer a Chat it was removed from.

**Blocked by:** 10, 11, 16.

**Status:** ready-for-human

- [x] The Chat list shows last message, unread count and ordering by last activity, and filters by participant name
- [x] A thread pages back through history without skipping or repeating a message
- [x] Composing shows the message immediately and reconciles with what the service confirms, using the client message id
- [x] A Staff-only Message is visibly marked when read, and composing one is a deliberate, visible choice
- [x] The three close codes are handled distinctly
- [x] After a reconnect the interface recovers its own state, leaving no gap in what the user sees
- [x] The interface is usable at phone width (unchanged `ChatsLayout` breakpoint/Drawer; not manually verified in a live browser — see comments)

## Comments

**Scope discovery, resolved with the user before implementing:** the existing frontend (`Sidebar`, `ChatThread`, `api.ts`) predated this service's real contract and called endpoints that don't exist here — `GET /users` (no such route), `POST /chats` from the browser (composition is monolith-only, ticket 05/ADR), and `/auth/me` in a shape (`{id,email,username}`) that doesn't match `CallerRead`. Resolved by: removing the "Nova chat" create-flow entirely (not this ticket's job — composition arrives as a monolith command), fixing `getMe`'s shape to match `CallerRead`, and resolving an unnamed 1:1 chat's label off `last_message.sender_display_name` instead of a roster lookup.

**Design decisions confirmed with the user:** unread state is now entirely server-driven (`unread_count` + `POST /chats/{id}/read`), replacing the old `localStorage` cursor (`lastSeen.ts`, deleted); Staff-only compose is a checkbox + tinted bubble with an "Interno" tag; pagination on both the chat list and the thread is infinite-scroll; reconnects are silent (no banner).

**Bug found and fixed via testing:** the read-state mutation's `mutationFn` originally closed over `chatId`/`token` directly. Since it's invoked from a `useEffect` cleanup that can fire *after* React Router has already re-rendered the same `ChatThread` instance for a new `chatId` (React Router doesn't remount on a param-only change), and TanStack Query rebinds `mutationFn` to the latest render on every render, the "mark the chat I'm leaving as read" call was silently attributed to the chat just entered instead. Fixed by threading `chatId`/`token` through the mutation's variables rather than its closure. Covered by a regression test in `ChatThread.test.tsx` and `ChatsLayout.test.tsx`.

**Not manually browser-verified:** all behavior is covered by Vitest + Testing Library (131 tests, full suite green) plus `tsc -b` and `vite build`, but the app was not launched in a live browser this session — phone-width usability in particular should get a real visual check.

**`/code-review medium` findings, post-implementation:** 4 of 5 findings were real and fixed, each with a regression test first:
- `useResilientSocket`: a TOKEN_EXPIRED reconnect's pending `refreshToken()` wasn't guarded against a deliberate close, so navigating away mid-refresh leaked a socket. Fixed by checking `deliberateClose` before reconnecting (and before the in-band renewal's `send`).
- `ChatThread`: the optimistic bubble's `sender_id` came only from `getMe`, so a message sent before that query resolved rendered as an external/bot message. Fixed with `getUserId` (decodes the token's own `sub` claim, jwt.ts) as a synchronous fallback.
- `ChatThread`: a failed send's `onError` unconditionally restored the failed text into the compose box, clobbering a newer draft typed while the send was in flight. Fixed with a functional update that only restores into a still-empty box.
- `ChatThread`: `prevScrollHeightRef` (older-page scroll preservation) was only cleared on a page-count change, so a failed `fetchNextPage()` left it stale for the next attempt. Fixed by keying the clear on the fetch settling instead — applied directly without a dedicated test (self-correcting, cosmetic-only; a deterministic repro needs wrestling with React Query's default retry/backoff timing for a low payoff).
- The 5th finding (`chatLabel` only resolving an unnamed 1:1's name from the other participant's *own* last message, not whichever side spoke last) is the literal behavior the user approved up front — not a bug, left as-is.
