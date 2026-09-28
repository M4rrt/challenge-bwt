# 12 — Presence and typing

**What to build:** A Participant sees who is online and who is typing, so they know whether to expect an answer now and whether to wait.

Presence stays pure Redis with no table behind it, and keeps the property the source module had: when the presence store is gone, presence degrades to unknown rather than breaking the Chat. Messaging must not depend on it.

**Blocked by:** 07.

**Status:** done

- [x] A Participant's presence is visible to the other Participants of their Chats
- [x] Typing is announced to the Chat and expires on its own without an explicit stop
- [x] Presence and typing never cross a Company
- [x] With the presence store unavailable, presence reports unknown and sending and reading messages keep working
- [x] Presence has no table behind it

## Comments

Implemented as a push protocol over the existing chat WebSocket (`app/services/presence.py`, `app/services/connection.py`, `app/routers/websocket.py`):

- `presence.online` / `presence.offline` broadcast to the Chat's own address on the first connection in and the last one out, ref-counted per (Company, Chat, user) in Redis with a TTL refreshed on the same revalidation tick `connection.py` already runs.
- `presence.snapshot` sent once to a newly connected socket, naming who else is already online (`known: false` when the store could not answer).
- `typing` is a client→server→Chat relay with no Redis key at all: each announcement carries `expires_at`, and the client lets its own indicator lapse rather than waiting for an explicit stop.

Fixed two pre-existing races in `app/services/realtime.py` surfaced by presence's much higher connect/disconnect broadcast frequency: an unhandled send to an already-disconnected socket could crash `run_subscriber` for the whole instance, and `connections_for` iterated its live index rather than a copy. Both are now defensive the same way `close_quietly` already was for closes.

`/code-review` (medium) then found three real bugs in the first pass, all fixed:
- `Connection` was calling `presence.leave` unconditionally on disconnect even when its own `presence.join` had failed open (store briefly unreachable) — a decrement that was never earned could zero out a sibling tab's real count and announce that person offline while the sibling was still connected. `Connection` now tracks whether its own `join` actually succeeded and only `leave`s if it did.
- `presence.leave`'s decrement-then-maybe-delete was two Redis round trips, leaving a window where a concurrent `join` could set the key back to 1 only for the still-pending `delete` to erase it. Replaced with one atomic Lua script (`DECR` then `DEL` at zero, run as a single command Redis cannot interleave anything into).
- `_deliver_quietly` only suppressed `RuntimeError`/`WebSocketDisconnect`/`anyio.ClosedResourceError`; a dead TCP connection can also surface as `anyio.BrokenResourceError` or a bare `OSError` (broken pipe) at the transport, which would still have crashed `run_subscriber`. Both are now suppressed too.
