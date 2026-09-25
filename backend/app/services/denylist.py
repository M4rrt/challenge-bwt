"""A credential the service stops believing before it expires.

The normal path is not here. ADR-0011 made the fifteen-minute token the
revocation mechanism: the monolith revokes by not issuing the next one, and the
service asks nobody anything. This is the exception the ADR carved out for the
cases where fifteen minutes is too long — a dismissal, a ban, a credential
believed leaked.

**Every entry expires alongside the token it blocks.** That is what stops this
being the distributed revocation list the ADR refused. Nothing prunes it, nothing
grows without bound, and no entry can outlive the credential it is about, so the
list has no memory of anything that would be rejected anyway. A user entry lives
for the longest a token can, because the service holds no record of what the
monolith issued and so cannot know which of that person's tokens are still out.

It lives in Redis, which the service already runs for fan-out, and it is read on
the WebSocket paths: at the handshake, at every in-band renewal, and at every
periodic revalidation. It is deliberately *not* read on the API path — see
"Débito técnico conhecido" in `README.md`, which records what that costs.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller, verify_chat_token
from app.core.config import settings
from app.schemas.revocation import RevocationEvent
from app.services.outbox import enqueue_eviction

logger = logging.getLogger(__name__)

redis_client: redis.Redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def user_key(company_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Everything that person holds, in this Company.

    The Company is in the key for the reason every fan-out address carries it:
    the same user id can exist in two of them, and a ban in one is not a ban in
    the other.
    """
    return f"denylist:user:{company_id}:{user_id}"


def token_key(token: str) -> str:
    """One credential, by digest rather than by value.

    The token is a bearer credential, and a denylist is the wrong place to keep a
    working copy of one: its whole job is to be readable by whatever asks. The
    digest answers "is it this one" and nothing else.
    """
    return f"denylist:token:{hashlib.sha256(token.encode()).hexdigest()}"


async def deny_user(company_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Block everything that person holds, for as long as any of it could still be good.

    One lifetime, because the service holds no record of what the monolith
    issued: it cannot know which of their tokens are still out, only that none
    can outlive a lifetime from now.
    """
    await redis_client.set(user_key(company_id, user_id), "1", ex=settings.chat_token_ttl_seconds)


async def deny_token(token: str) -> None:
    """Block one credential for whatever life it has left.

    A token the service cannot verify is blocked for the full lifetime instead of
    being refused: it is already worthless, the monolith is delivering
    at-least-once, and an error here would be retried forever over a credential
    nothing accepts.
    """
    caller = verify_chat_token(token)
    remaining = (
        int((caller.expires_at - datetime.now(timezone.utc)).total_seconds())
        if caller is not None
        else settings.chat_token_ttl_seconds
    )
    await redis_client.set(token_key(token), "1", ex=max(1, remaining))


async def is_denied(caller: Caller, token: str) -> bool:
    """Whether either the person or this one credential has been taken away.

    One round trip for both keys. It is asked often enough — every handshake and
    once a minute per open connection — that two would be two.

    **A Redis that cannot answer answers no.** It is asked on every handshake and
    once a minute per open connection, so letting the error out would turn a Redis
    outage into every connection being closed and no new one opening — which is
    strictly worse than what the same outage does today, where sockets stay up and
    the outbox holds its rows until it returns.

    Failing open on a revocation list is a real choice and it is the smaller one
    here, for two reasons. This is the exception path: the normal revocation is the
    token's own lifetime and it is unaffected. And during that outage there is no
    fan-out at all — the connection that stayed open receives nothing, because the
    subscriber it would arrive through is gone too.
    """
    try:
        return bool(
            await redis_client.exists(user_key(caller.company_id, caller.id), token_key(token))
        )
    except RedisError:
        logger.warning("denylist unreachable; letting a credential through", exc_info=True)
        return False


async def apply_revocation(db: AsyncSession, event: RevocationEvent) -> None:
    """Carry out one revocation: stop believing the credential, and close what it holds.

    The two halves are not symmetric, and the schema's either/or is why. Banning a
    *person* also evicts, because every connection they hold is now somebody
    else's problem to reopen; blocking one *token* does not, because the sockets
    are indexed by who holds them and not by which string they presented, so there
    is nothing to look the leaked credential up by. That connection closes at its
    next revalidation instead.

    The denylist write lands before the eviction row, and deliberately: Redis is
    not in this transaction, so the order that can be chosen is the one where the
    door is shut before anybody is pushed through it. The reverse would leave a
    window in which an evicted socket reconnects and is let in.
    """
    if event.token is not None:
        await deny_token(event.token)

    if event.user_id is not None:
        await deny_user(event.company_id, event.user_id)
        enqueue_eviction(db, event.company_id, event.user_id)
        await db.commit()
