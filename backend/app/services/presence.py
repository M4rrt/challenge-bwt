"""Who is online in a Chat right now, kept in Redis and nowhere else.

The source module's presence was pure Redis with no table behind it, and this
keeps that property on purpose: presence is a fact about *this instant*, not a
record anybody needs after the connection that made it true has gone. A table
would need pruning, a migration, and a second place that can disagree with the
sockets actually open.

**One counter per (Company, Chat, user).** Two connections from the same person
in the same Chat — two tabs — must not tell everyone else they went offline the
moment one of the tabs closes, so presence is a count of open connections, not a
flag. It reaches zero only when the last one has.

**The Company is in the key** for the same reason it is in every fan-out
address: the same user id can exist in two Companies, and presence answered for
one must not leak into the other.

**A Redis that cannot answer answers "I don't know", not "offline".** Reporting
someone offline is a claim as strong as reporting them online, and this store
cannot support either one while it is unreachable. Every function here logs and
returns a value meaning "unknown" rather than raising, so a presence outage
never becomes a reason a connection cannot open or a message cannot send —
messaging does not read this module at all.
"""

import logging
import uuid
from collections.abc import Iterable

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

redis_client: redis.Redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)

PRESENCE_TTL_SECONDS = 120
"""How long a connection's presence survives without being refreshed.

Longer than `REVALIDATION_INTERVAL` (60s, `app/services/connection.py`), which
is what refreshes it on every open connection without a timer of its own — so an
ordinary connection never lets its key expire. It exists at all only for the
connection that never gets to say goodbye: a killed process leaves no `finally`
to run, and this is what stops that person from reading as online forever.
"""

ONLINE = "presence.online"
"""Server → Chat: this Company's presence for a user in this Chat just started."""

OFFLINE = "presence.offline"
"""Server → Chat: it just ended — their last connection to this Chat closed."""

SNAPSHOT = "presence.snapshot"
"""Server → the connecting client only: who else is online here right now."""


def _key(company_id: uuid.UUID, chat_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"presence:{company_id}:{chat_id}:{user_id}"


_LEAVE_SCRIPT = """
local count = redis.call("DECR", KEYS[1])
if count <= 0 then
    redis.call("DEL", KEYS[1])
end
return count
"""
"""Decrement and, at zero, delete — as the one command Redis actually runs.

See `leave`'s docstring for the race this closes: a plain `DECR` followed by a
separate `DELETE` leaves a window between them that a concurrent `join` can
land in.
"""


async def join(company_id: uuid.UUID, chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """One more open connection for this person in this Chat. True the moment it is the first.

    Only the first of somebody's connections is worth announcing — the second
    tab opening is not news to anyone else in the Chat.
    """
    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.incr(_key(company_id, chat_id, user_id))
            pipe.expire(_key(company_id, chat_id, user_id), PRESENCE_TTL_SECONDS)
            count, _ = await pipe.execute()
    except RedisError:
        logger.warning("presence store unreachable; not announcing this connection", exc_info=True)
        return False
    return count == 1


async def refresh(company_id: uuid.UUID, chat_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Push the deadline back out, on the same schedule an open connection already runs.

    A missing key is left missing: refreshing something that is not there would
    resurrect a count a failed `join` or `leave` never got to keep straight, and
    the connection that should have kept it alive will `join` again if it is
    ever asked whether it still belongs.
    """
    try:
        await redis_client.expire(_key(company_id, chat_id, user_id), PRESENCE_TTL_SECONDS)
    except RedisError:
        logger.warning("presence store unreachable; a key may expire before its connection closes", exc_info=True)


async def leave(company_id: uuid.UUID, chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """One fewer open connection. True the moment none are left.

    The key is deleted rather than left at zero: an index that never forgets a
    key it no longer needs is the same growth-without-bound `ConnectionManager`
    already avoids for the same reason.

    The decrement and the delete are one Lua script, not two round trips. Redis
    runs a script the same way it runs any single command — to completion,
    before anything else touches the key — so a `join` from a new connection of
    this same person cannot land between them. Two round trips could: a `join`
    landing after the `DECR` but before the `DELETE` would set the key back to 1
    only for the pending `DELETE` to erase it, leaving that new connection
    invisible to `who_is_online` until it reconnects.
    """
    key = _key(company_id, chat_id, user_id)
    try:
        count = await redis_client.eval(_LEAVE_SCRIPT, 1, key)
    except RedisError:
        logger.warning("presence store unreachable; not announcing this disconnect", exc_info=True)
        return False
    return count <= 0


async def who_is_online(
    company_id: uuid.UUID, chat_id: uuid.UUID, user_ids: Iterable[uuid.UUID]
) -> list[uuid.UUID] | None:
    """Which of these people currently hold a connection to this Chat, or `None` for "unknown".

    `None` and `[]` are different answers and a caller must not conflate them: an
    empty list is "asked, and nobody is online"; `None` is "could not ask". A
    snapshot built from either without telling them apart would show an
    outage as a Chat where everyone happens to be offline.
    """
    ids = list(user_ids)
    if not ids:
        return []
    try:
        values = await redis_client.mget([_key(company_id, chat_id, uid) for uid in ids])
    except RedisError:
        logger.warning("presence store unreachable; reporting unknown", exc_info=True)
        return None
    return [uid for uid, value in zip(ids, values) if value is not None]
