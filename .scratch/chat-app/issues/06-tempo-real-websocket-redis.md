# 06 — Entrega em tempo real (WebSocket + Redis)

**What to build:** A connected participant receives new messages live over WebSocket, without polling — the mandatory real-time requirement. Implements ADR-0001 (WebSocket in-app, not API Gateway) and ADR-0003 (Redis pub/sub for horizontal fan-out).

**Blocked by:** 05.

**Status:** done

- [x] WebSocket endpoint, authenticated via the JWT (query param on handshake, per the design session)
- [x] Connection manager: registry of open connections per conversation
- [x] On message send (ticket 05's endpoint), publish to a Redis channel keyed by `conversation_id`
- [x] Each app instance subscribes to Redis and forwards matching messages to its local connections
- [x] Tests: a message sent by one client arrives over WS for another connected participant; a non-participant's WS connection never receives it

## Comments

Implemented TDD (red-green per cycle), at two seams agreed with the user up front: (1) `GET /websocket/conversations/{id}` end-to-end with `POST /conversations/{id}/messages` — a connected participant receives the sent message over WS; (2) same endpoint, non-participant/invalid-token connection attempts are closed with code 1008 before `accept()`, never receiving anything. Internal collaborators (`ConnectionManager`, the extracted `decode_user_from_token`, the Redis publish payload) are exercised only indirectly through those two seams, not unit-tested directly.

- `app/routers/websocket.py` — `GET /websocket/conversations/{conversation_id}?token=<jwt>`. Validates the JWT and conversation membership *before* `websocket.accept()`; both failure modes close with the same code (1008), mirroring the existing 404-not-403 isolation logic for REST (`docs/decisions.md`) so a non-participant can't distinguish "wrong token" from "conversation doesn't exist." After accept, a `receive_json()` loop with a `match message_type: case _: pass` skeleton keeps the connection open (detects disconnect) without handling any client→server message types yet — left as a deliberate hook for a future feature (e.g. "typing…") per user request during grilling.
- `app/services/realtime.py` — module-level `ConnectionManager` (`conversation_id → set[WebSocket]`); `publish_message()` (shared client) called from `send_message` right after commit, so any future caller of `send_message` (ticket 07's webhook path included) gets broadcast for free without remembering to publish separately; `run_subscriber()` (separate Redis connection — pub/sub connections can't also `PUBLISH`) does a single global `PSUBSCRIBE conversation:*` rather than per-conversation subscribe/unsubscribe, avoiding a whole class of reference-counting races for the scale this app runs at.
- `app/main.py` — new `lifespan` handler starts/cancels the subscriber task around the app's life.
- `app/core/security.py` — extracted `decode_user_from_token(token, db) -> User | None` (no exception) out of `get_current_user`, shared by the HTTP dependency and the WS handshake, which can't use `HTTPException` after the handshake has started.
- `app/services/message.py` — `_assert_participant` renamed to `assert_participant` (unchanged behavior) so the WS router can reuse the same isolation check `send_message`/`list_messages` already share.
- Broadcast includes the sender's own connection if they're also connected (no per-connection user tracking) — relies on the frontend's TanStack Query cache being keyed by message `id` for idempotent dedup (`docs/decisions.md`).
- Test infra: added `httpx-ws` + `asgi-lifespan` dev deps. `tests/conftest.py`'s `client` fixture now runs the app's lifespan via `LifespanManager` so the Redis subscriber actually starts during tests (`REDIS_URL` already points at the docker-compose Redis container — tests run against the real thing, no mocking, per ADR-0003). WS-specific tests build a second, `ASGIWebSocketTransport`-backed client *inline inside the test body* rather than as a fixture — that transport opens an `anyio` task group in `__aenter__`/`__aexit__`, which can't span a pytest-asyncio fixture's yield boundary (enter and exit end up in different asyncio Tasks); keeping it local to the test's own coroutine avoided a `RuntimeError: Attempted to exit cancel scope in a different task`.

All 32 backend tests pass (30 pre-existing + 2 new), including 5 repeated runs of the new WS tests to rule out timing flakiness in the accept→register→publish→receive path.
