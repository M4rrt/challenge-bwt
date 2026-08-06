import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ConversationParticipant
from app.models.message import Message
from app.models.user import User
from app.schemas.message import MessageCreate


class ConversationNotFoundError(Exception):
    pass


async def _assert_participant(
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


async def send_message(
    db: AsyncSession, current_user: User, conversation_id: uuid.UUID, data: MessageCreate
) -> Message:
    await _assert_participant(db, conversation_id, current_user.id)

    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        sender_type="user",
        body=data.body,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def list_messages(
    db: AsyncSession, current_user: User, conversation_id: uuid.UUID
) -> list[Message]:
    await _assert_participant(db, conversation_id, current_user.id)

    result = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.all())
