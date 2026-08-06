import uuid
from collections import defaultdict

import redis.asyncio as redis
from fastapi import WebSocket

from app.core.config import settings
from app.models.message import Message
from app.schemas.message import MessageRead

CHANNEL_PATTERN = "conversation:*"


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    def connect(self, conversation_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[conversation_id].add(websocket)

    def disconnect(self, conversation_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[conversation_id].discard(websocket)
        if not self._connections[conversation_id]:
            del self._connections[conversation_id]

    def connections_for(self, conversation_id: uuid.UUID) -> set[WebSocket]:
        return self._connections.get(conversation_id, set())


connection_manager = ConnectionManager()

_publish_client: redis.Redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _channel_for(conversation_id: uuid.UUID) -> str:
    return f"conversation:{conversation_id}"


async def publish_message(message: Message) -> None:
    payload = MessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_type=message.sender_type,
        source_label=message.source_label,
        body=message.body,
        created_at=message.created_at,
    ).model_dump_json()
    await _publish_client.publish(_channel_for(message.conversation_id), payload)


async def run_subscriber() -> None:
    subscriber_client: redis.Redis = redis.Redis.from_url(
        settings.redis_url, decode_responses=True
    )
    pubsub = subscriber_client.pubsub()
    await pubsub.psubscribe(CHANNEL_PATTERN)
    try:
        async for event in pubsub.listen():
            if event["type"] != "pmessage":
                continue
            conversation_id = uuid.UUID(event["channel"].removeprefix("conversation:"))
            for websocket in connection_manager.connections_for(conversation_id):
                await websocket.send_text(event["data"])
    finally:
        await pubsub.punsubscribe(CHANNEL_PATTERN)
        await pubsub.aclose()
        await subscriber_client.aclose()
