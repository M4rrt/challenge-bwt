import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message
from app.models.user import User
from app.schemas.message import MessageCreate, WebhookMessageCreate
from app.services.conversation import notify_participants
from app.services.realtime import publish_message


class ConversationNotFoundError(Exception):
    pass


async def assert_participant(
    db: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    participant = await db.scalar(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
    )
    if participant is None:
        raise ConversationNotFoundError()


async def _persist_and_publish(db: AsyncSession, message: Message) -> Message:
    db.add(message)
    await db.commit()
    await db.refresh(message)
    await publish_message(message)
    await notify_participants(db, message.conversation_id)
    return message


async def send_message(
    db: AsyncSession, current_user: User, conversation_id: uuid.UUID, data: MessageCreate
) -> Message:
    await assert_participant(db, conversation_id, current_user.id)

    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        sender_type="user",
        body=data.body,
    )
    return await _persist_and_publish(db, message)


async def assert_conversation_exists(db: AsyncSession, conversation_id: uuid.UUID) -> None:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise ConversationNotFoundError()


async def send_external_message(db: AsyncSession, data: WebhookMessageCreate) -> Message:
    await assert_conversation_exists(db, data.conversation_id)

    message = Message(
        conversation_id=data.conversation_id,
        sender_id=None,
        sender_type="external",
        source_label=data.source_label,
        body=data.body,
    )
    return await _persist_and_publish(db, message)


async def list_messages(
    db: AsyncSession, current_user: User, conversation_id: uuid.UUID
) -> list[Message]:
    await assert_participant(db, conversation_id, current_user.id)

    result = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.all())
