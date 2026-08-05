# 06 — Entrega em tempo real (WebSocket + Redis)

**What to build:** A connected participant receives new messages live over WebSocket, without polling — the mandatory real-time requirement. Implements ADR-0001 (WebSocket in-app, not API Gateway) and ADR-0003 (Redis pub/sub for horizontal fan-out).

**Blocked by:** 05.

**Status:** ready-for-agent

- [ ] WebSocket endpoint, authenticated via the JWT (query param on handshake, per the design session)
- [ ] Connection manager: registry of open connections per conversation
- [ ] On message send (ticket 05's endpoint), publish to a Redis channel keyed by `conversation_id`
- [ ] Each app instance subscribes to Redis and forwards matching messages to its local connections
- [ ] Tests: a message sent by one client arrives over WS for another connected participant; a non-participant's WS connection never receives it
