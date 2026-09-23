import asyncio
import uuid
from collections import defaultdict

import redis.asyncio as redis
from fastapi import WebSocket

from app.core.config import settings
from app.models.message import Message
from app.schemas.message import MessageRead

CHAT_CHANNEL_PATTERN = "chat:*"
USER_CHANNEL_PATTERN = "user:*"


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._user_connections: dict[tuple[uuid.UUID, uuid.UUID], set[WebSocket]] = (
            defaultdict(set)
        )

    def connect(self, chat_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[chat_id].add(websocket)

    def disconnect(self, chat_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[chat_id].discard(websocket)
        if not self._connections[chat_id]:
            del self._connections[chat_id]

    def connections_for(self, chat_id: uuid.UUID) -> set[WebSocket]:
        return self._connections.get(chat_id, set())

    def connect_user(
        self, company_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket
    ) -> None:
        self._user_connections[(company_id, user_id)].add(websocket)

    def disconnect_user(
        self, company_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket
    ) -> None:
        key = (company_id, user_id)
        self._user_connections[key].discard(websocket)
        if not self._user_connections[key]:
            del self._user_connections[key]

    def connections_for_user(
        self, company_id: uuid.UUID, user_id: uuid.UUID
    ) -> set[WebSocket]:
        return self._user_connections.get((company_id, user_id), set())


connection_manager = ConnectionManager()

_publish_client: redis.Redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _channel_for(chat_id: uuid.UUID) -> str:
    return f"chat:{chat_id}"


def _channel_for_user(company_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """The chat-list channel carries the Company, because a user id does not identify a reader.

    The same person can hold a token in two Companies. Keyed by user alone, a
    Chat summary published for one Company would land on the socket they opened
    with the other one's token.
    """
    return f"user:{company_id}:{user_id}"


async def publish_message(message: Message) -> None:
    payload = MessageRead(
        id=message.id,
        chat_id=message.chat_id,
        sender_id=message.sender_id,
        sender_type=message.sender_type,
        source_label=message.source_label,
        body=message.body,
        created_at=message.created_at,
    ).model_dump_json()
    await _publish_client.publish(_channel_for(message.chat_id), payload)


async def publish_to_user(company_id: uuid.UUID, user_id: uuid.UUID, payload: str) -> None:
    await _publish_client.publish(_channel_for_user(company_id, user_id), payload)


async def run_subscriber(subscribed: asyncio.Event | None = None) -> None:
    subscriber_client: redis.Redis = redis.Redis.from_url(
        settings.redis_url, decode_responses=True
    )
    pubsub = subscriber_client.pubsub()
    await pubsub.psubscribe(CHAT_CHANNEL_PATTERN, USER_CHANNEL_PATTERN)
    if subscribed is not None:
        subscribed.set()
    try:
        async for event in pubsub.listen():
            if event["type"] != "pmessage":
                continue
            channel = event["channel"]
            if channel.startswith("chat:"):
                chat_id = uuid.UUID(channel.removeprefix("chat:"))
                for websocket in connection_manager.connections_for(chat_id):
                    await websocket.send_text(event["data"])
            elif channel.startswith("user:"):
                company_id, user_id = (
                    uuid.UUID(part) for part in channel.removeprefix("user:").split(":")
                )
                for websocket in connection_manager.connections_for_user(company_id, user_id):
                    await websocket.send_text(event["data"])
    finally:
        await pubsub.punsubscribe(CHAT_CHANNEL_PATTERN, USER_CHANNEL_PATTERN)
        await pubsub.aclose()
        await subscriber_client.aclose()
