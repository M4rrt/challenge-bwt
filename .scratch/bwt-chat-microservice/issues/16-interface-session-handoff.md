# 16 — Interface: session handoff

**What to build:** A Company staff member clicks chat in the BWT product and lands in the Chat interface already signed in, never typing a second password. The interface takes a single-use, short-lived exchange code from the URL fragment, redeems it against the monolith, and keeps the chat-scoped credential it gets back — never the product's session.

The redemption response also says where the service lives. The API and WebSocket URLs become runtime state rather than a build-time constant, which is what makes it possible to move the service or switch it off without shipping a new version of any client — and the native apps, which consume the same service, cannot be updated on demand.

**Blocked by:** 01.

**Status:** ready-for-human

- [x] The interface's own registration and login screens are deleted
- [x] A redemption route reads the exchange code from the URL fragment and POSTs it to the monolith
- [x] The code is never persisted anywhere and never appears in a query string
- [x] The chat-scoped credential is stored and buys chat tokens for as long as the session lasts
- [x] The API and WebSocket base URLs come from the redemption response at runtime; the build-time environment variable survives only as a development fallback
- [x] The existing silent-refresh path is retargeted at the chat token rather than the service's removed refresh endpoint
- [x] A failed or already-used redemption shows an error and does not leave the interface in a half-authenticated state

## Comments

**The monolith's exact redemption/token-issue contract is not settled anywhere this repo can read** — it lives in `brwinetours-backend-development`, not here. Built against an assumed shape, to be reconciled once that side lands:

- `VITE_MONOLITH_URL` (new env var, dev fallback `http://localhost:3000`) — separate from `VITE_API_URL`, since the monolith's own address is fixed and the chat service's is what redemption makes dynamic.
- `POST {MONOLITH_URL}/chat/sessions/redeem` `{ code }` → `{ renewal_token, api_url, ws_url }` — matches ADR-0006 literally: redemption yields the renewal credential and the service's addresses, not a chat token.
- `POST {MONOLITH_URL}/chat/sessions/token` `{ renewal_token }` → `{ access_token, token_type }` — the same call mints the *first* chat token and every renewal, so the silent-refresh retarget (`AuthContext`'s handler) and the entry flow (`SessionHandoff`) share one function, `issueChatToken`.
- Fragment format assumed to be `#code=<value>`, read via `URLSearchParams` and stripped with `history.replaceState` before the redemption call fires — never a query string, never persisted.

**No half-authenticated state, by construction, not by cleanup.** `SessionHandoff` chains redemption → token purchase in one mutation and only calls `auth.login(...)` in `onSuccess`; either call failing leaves nothing written to `localStorage` at all, rather than storing-then-rolling-back.

**Registration/login backend endpoints were already gone** (ticket 01 deleted them); this ticket only had to stop the interface calling them. `logoutRequest` (the interface's `/auth/logout` call) is deleted with them — no ticket asked for a monolith-side revocation call on logout, so logout is now purely local: clear the chat token and renewal token, nothing remote.

**Everything reachable only after this ticket** (ticket 17: chat list contract, unread counts, the three close codes, pagination) **is untouched** — `Sidebar`/`ChatThread` still call the same `/chats`, `/users`, `/messages` endpoints they did before, just against the runtime `getApiUrl()`/`getWsUrl()` instead of a build-time constant.
