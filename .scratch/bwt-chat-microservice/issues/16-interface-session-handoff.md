# 16 — Interface: session handoff

**What to build:** A Company staff member clicks chat in the BWT product and lands in the Chat interface already signed in, never typing a second password. The interface takes a single-use, short-lived exchange code from the URL fragment, redeems it against the monolith, and keeps the chat-scoped credential it gets back — never the product's session.

The redemption response also says where the service lives. The API and WebSocket URLs become runtime state rather than a build-time constant, which is what makes it possible to move the service or switch it off without shipping a new version of any client — and the native apps, which consume the same service, cannot be updated on demand.

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] The interface's own registration and login screens are deleted
- [ ] A redemption route reads the exchange code from the URL fragment and POSTs it to the monolith
- [ ] The code is never persisted anywhere and never appears in a query string
- [ ] The chat-scoped credential is stored and buys chat tokens for as long as the session lasts
- [ ] The API and WebSocket base URLs come from the redemption response at runtime; the build-time environment variable survives only as a development fallback
- [ ] The existing silent-refresh path is retargeted at the chat token rather than the service's removed refresh endpoint
- [ ] A failed or already-used redemption shows an error and does not leave the interface in a half-authenticated state
