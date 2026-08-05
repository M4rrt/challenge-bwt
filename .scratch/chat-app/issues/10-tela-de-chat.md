# 10 — Tela de chat

**What to build:** Opening a conversation shows its message backlog and new messages appear live, without a page refresh — the end-to-end demoable proof of the mandatory real-time requirement.

**Blocked by:** 09, 06.

**Status:** ready-for-agent

- [ ] On open, fetch message backlog via ticket 05's REST endpoint (TanStack Query)
- [ ] Open a WebSocket connection (ticket 06) for the active conversation; incoming messages pushed into the same TanStack Query cache as the backlog (per `docs/decisions.md`'s frontend-tooling decision)
- [ ] Send-message input posts via REST and/or WS per the backend's chosen path
- [ ] Tests: backlog renders on open, a message sent from another session appears live without a manual refresh
