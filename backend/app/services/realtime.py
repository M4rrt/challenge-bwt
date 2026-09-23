"""The three fan-out addresses, and the connections listening on each.

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

The Company is in all three addresses. For a user it is load-bearing, because
the same user id can exist in two Companies and a summary published for one
would otherwise land on the socket opened with the other's token. For a Chat it
is belt over an already-fastened belt — a Chat id is unique on its own — and it
is there because the rule in `README.md` is that a fan-out path carries the
Company in the channel key, with no exceptions to remember.
"""

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

import redis.asyncio as redis
from fastapi import WebSocket

from app.core.config import settings

CHANNEL_PATTERNS = ("chat:*", "user:*")


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


class ConnectionManager:
    """Which local sockets are listening on which address.

    Keyed by the address itself rather than by Chat or by user, because that is
    all the delivery path needs to know. A socket joins the addresses its
    holder is entitled to when it opens; after that, routing is a dictionary
    lookup on the channel name and there is no second place where entitlement
    could be decided differently.
    """

    def __init__(self) -> None:
        self._by_address: dict[str, set[WebSocket]] = defaultdict(set)

    def connect(self, addresses: Iterable[Address], websocket: WebSocket) -> None:
        for address in addresses:
            self._by_address[address.channel].add(websocket)

    def disconnect(self, addresses: Iterable[Address], websocket: WebSocket) -> None:
        for address in addresses:
            self._by_address[address.channel].discard(websocket)
            if not self._by_address[address.channel]:
                del self._by_address[address.channel]

    def connections_for(self, channel: str) -> set[WebSocket]:
        """Keyed by the channel rather than the Address, because that is what arrives.

        A frame comes back from Redis carrying a channel name and nothing else,
        so the lookup has to be answerable from a string.
        """
        return self._by_address.get(channel, set())


connection_manager = ConnectionManager()

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
            for websocket in connection_manager.connections_for(event["channel"]):
                await websocket.send_text(event["data"])
    finally:
        await pubsub.punsubscribe(*CHANNEL_PATTERNS)
        await pubsub.aclose()
        await subscriber_client.aclose()
