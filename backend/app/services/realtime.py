"""The three fan-out addresses, the connections listening on each, and who holds them.

Delivery is addressed to one of three groups: what is computed for a single
user, what is true for everyone in a Chat, and what is true only for the
Company's staff in it. A Staff-only Message goes to the staff address and
nowhere else.

**Isolation comes from the address.** Nothing on this path reads a rule or
applies a filter: who may see a payload was settled when it was addressed, and
the subscriber below forwards by channel name without knowing what a Chat or a
user kind is. That is the point — the alternative is one group per Chat plus an
`if` at delivery, and the `if` is what every future emitter has to remember to
write. ADR-0008's defect was exactly a rule evaluated in more than one place.

A fourth channel carries no payload at all. `control:{company}` is how an
eviction reaches the instance holding a connection — which is almost never the
one that handled the removal — and the subscriber tells it apart by its prefix
rather than by reading inside a frame. The two indexes below answer the two
different questions: `_by_address` who is listening here, `_by_holder` and
`_by_user` which of one person's connections must go.

The Company is in all three addresses. For a user it is load-bearing, because
the same user id can exist in two Companies and a summary published for one
would otherwise land on the socket opened with the other's token. For a Chat it
is belt over an already-fastened belt — a Chat id is unique on its own — and it
is there because the rule in `README.md` is that a fan-out path carries the
Company in the channel key, with no exceptions to remember.
"""

import asyncio
import contextlib
import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass
from typing import TypeVar

import redis.asyncio as redis
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.close_codes import CloseCode
from app.core.config import settings
from app.schemas.eviction import Eviction

CONTROL_PREFIX = "control:"
CHANNEL_PATTERNS = ("chat:*", "user:*", f"{CONTROL_PREFIX}*")

logger = logging.getLogger(__name__)

Key = TypeVar("Key")


@dataclass(frozen=True)
class Address:
    """Somewhere to deliver to, and the Company it belongs to.

    The two travel together because they cannot be allowed to disagree. Passed
    apart, a caller could write an outbox row filed under one Company and
    addressed into another's channel — and since the whole design rests on the
    channel being the isolation, that row would be a leak nothing downstream
    could catch.

    Only these three constructors build one, so `channel`'s shape is stated in
    exactly one place per address kind.
    """

    company_id: uuid.UUID
    channel: str


def address_for_chat(company_id: uuid.UUID, chat_id: uuid.UUID) -> Address:
    """Everyone in the Chat."""
    return Address(company_id, f"chat:{company_id}:{chat_id}")


def address_for_chat_staff(company_id: uuid.UUID, chat_id: uuid.UUID) -> Address:
    """Only the Company's staff in the Chat."""
    base = address_for_chat(company_id, chat_id)
    return Address(company_id, f"{base.channel}:staff")


def address_for_user(company_id: uuid.UUID, user_id: uuid.UUID) -> Address:
    """One user, wherever they are — what their chat list is kept live from."""
    return Address(company_id, f"user:{company_id}:{user_id}")


def address_for_control(company_id: uuid.UUID) -> Address:
    """Not an audience: every instance, about its own sockets.

    Eviction has to reach the instance holding the connection, which is almost
    never the one that handled the removal, so it travels the same Redis path as
    a delivery. It gets a prefix of its own because the subscriber must be able
    to tell an instruction from a payload by the channel it arrived on — reading
    a `type` out of every frame would put a rule back on the delivery path.
    """
    return Address(company_id, f"{CONTROL_PREFIX}{company_id}")


@dataclass(frozen=True)
class Holder:
    """Whose connection this is, and which Chat it is in. `None` is their own socket.

    The eviction index's key, and it is a different question from delivery.
    Delivery asks "who is listening on this channel"; eviction asks "which of
    this person's connections must go" — and that cannot be answered from a
    channel name, because a token stays valid for everything except the Chat
    that was taken away.
    """

    company_id: uuid.UUID
    user_id: uuid.UUID
    chat_id: uuid.UUID | None = None


class ConnectionManager:
    """Which local sockets are listening where, and whose they are.

    Two questions, so two indexes, and keeping them apart is the point.

    **Delivery** is `_by_address`, keyed by the address and nothing else, because
    that is all the delivery path needs to know. A socket joins the addresses its
    holder is entitled to when it opens; after that, routing is a dictionary
    lookup on the channel name and there is no second place where entitlement
    could be decided differently.

    **Eviction** is `_by_holder` and `_by_user`, and it cannot be answered from an
    address. "Close this person's connections in this one Chat, and leave their
    other connections alone" names sockets, not an audience, and no channel name
    expresses it. `_by_holder` answers the one Chat; `_by_user` answers a ban,
    where every connection they hold goes.
    """

    def __init__(self) -> None:
        self._by_address: dict[str, set[WebSocket]] = defaultdict(set)
        self._by_holder: dict[Holder, set[WebSocket]] = defaultdict(set)
        self._by_user: dict[tuple[uuid.UUID, uuid.UUID], set[WebSocket]] = defaultdict(set)

    def connect(
        self, addresses: Iterable[Address], websocket: WebSocket, holder: Holder | None = None
    ) -> None:
        for address in addresses:
            self._by_address[address.channel].add(websocket)
        if holder is not None:
            self._by_holder[holder].add(websocket)
            self._by_user[holder.company_id, holder.user_id].add(websocket)

    def disconnect(
        self, addresses: Iterable[Address], websocket: WebSocket, holder: Holder | None = None
    ) -> None:
        for address in addresses:
            self._forget(self._by_address, address.channel, websocket)
        if holder is not None:
            self._forget(self._by_holder, holder, websocket)
            self._forget(self._by_user, (holder.company_id, holder.user_id), websocket)

    @staticmethod
    def _forget(
        index: MutableMapping[Key, set[WebSocket]], key: Key, websocket: WebSocket
    ) -> None:
        """Drop the socket, and the key with it once nothing is left under it.

        Emptied keys are deleted rather than kept: a `defaultdict` read grows it,
        so an index that never forgets a key would grow by one entry per Chat
        anybody ever opened a socket on.
        """
        if key not in index:
            return
        index[key].discard(websocket)
        if not index[key]:
            del index[key]

    def connections_for(self, channel: str) -> set[WebSocket]:
        """Keyed by the channel rather than the Address, because that is what arrives.

        A frame comes back from Redis carrying a channel name and nothing else,
        so the lookup has to be answerable from a string.
        """
        return self._by_address.get(channel, set())

    def connections_of(self, holder: Holder) -> set[WebSocket]:
        """That person's connections in that one Chat — a copy, because callers close them."""
        return set(self._by_holder.get(holder, ()))

    def every_connection_of(self, company_id: uuid.UUID, user_id: uuid.UUID) -> set[WebSocket]:
        """Everything that person holds here: each Chat they have open, and their own socket."""
        return set(self._by_user.get((company_id, user_id), ()))


connection_manager = ConnectionManager()


async def close_quietly(websocket: WebSocket, code: CloseCode) -> None:
    """Close, and do not mind a socket that has already gone.

    More than one thing can decide to close the same connection — its own
    deadline, an eviction arriving from another instance, the client itself
    hanging up — and whichever gets there second must not raise. Starlette
    treats a send after a close as a programming error, which here it is not.
    """
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await websocket.close(code=code)


_publish_client: redis.Redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


async def publish(channel: str, payload: str) -> None:
    """Put a payload on a channel. Only the drain calls this.

    It takes the channel as a string because that is what the drain has: the
    row it is paying was addressed when it was written, and what it stored is
    the channel.

    A request that called it directly would be announcing something its own
    transaction might still roll back, which is what the outbox exists to stop.
    """
    await _publish_client.publish(channel, payload)


async def carry_out(instruction: str) -> None:
    """Close what an eviction names, on this instance.

    The only thing on the delivery path that reads a payload, and it is allowed
    to because it is not deciding who may see something — that was settled when
    the row was addressed. It is being told which sockets to hang up.

    A malformed instruction is logged and dropped. The alternative is letting it
    out of the subscriber, and a subscriber that dies stops delivering everything
    for this instance, in silence.
    """
    try:
        eviction = Eviction.model_validate_json(instruction)
    except ValidationError:
        logger.warning("dropped an eviction this service cannot read: %s", instruction)
        return

    going = (
        connection_manager.every_connection_of(eviction.company_id, eviction.user_id)
        if eviction.chat_id is None
        else connection_manager.connections_of(
            Holder(eviction.company_id, eviction.user_id, eviction.chat_id)
        )
    )
    for websocket in going:
        await close_quietly(websocket, CloseCode.ACCESS_REVOKED)


async def run_subscriber(subscribed: asyncio.Event | None = None) -> None:
    subscriber_client: redis.Redis = redis.Redis.from_url(
        settings.redis_url, decode_responses=True
    )
    pubsub = subscriber_client.pubsub()
    await pubsub.psubscribe(*CHANNEL_PATTERNS)
    if subscribed is not None:
        subscribed.set()
    try:
        async for event in pubsub.listen():
            if event["type"] != "pmessage":
                continue
            if event["channel"].startswith(CONTROL_PREFIX):
                await carry_out(event["data"])
                continue
            for websocket in connection_manager.connections_for(event["channel"]):
                await websocket.send_text(event["data"])
    finally:
        await pubsub.punsubscribe(*CHANNEL_PATTERNS)
        await pubsub.aclose()
        await subscriber_client.aclose()
