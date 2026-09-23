import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.models.chat import STILL_IN_THE_CHAT, Chat, Participant
from app.models.message import Message
from app.schemas.message import MessageCreate, WebhookMessageCreate
from app.services.chat import notify_participants
from app.services.realtime import publish_message


class ChatNotFoundError(Exception):
    pass


async def assert_participant(
    db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    participant = await db.scalar(
        scope.select(Participant).where(
            Participant.chat_id == chat_id,
            Participant.user_id == user_id,
            STILL_IN_THE_CHAT,
        )
    )
    if participant is None:
        raise ChatNotFoundError()


async def _persist_and_publish(
    db: AsyncSession, scope: CompanyScope, message: Message
) -> Message:
    db.add(message)
    await db.commit()
    await db.refresh(message)
    await publish_message(message)
    await notify_participants(db, scope, message.chat_id)
    return message


async def send_message(
    db: AsyncSession,
    scope: CompanyScope,
    caller: Caller,
    chat_id: uuid.UUID,
    data: MessageCreate,
) -> Message:
    await assert_participant(db, scope, chat_id, caller.id)

    message = Message(
        company_id=caller.company_id,
        chat_id=chat_id,
        sender_id=caller.id,
        sender_type="user",
        body=data.body,
    )
    return await _persist_and_publish(db, scope, message)


async def assert_chat_exists(
    db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID
) -> Chat:
    chat = await db.scalar(
        scope.select(Chat).where(Chat.id == chat_id)
    )
    if chat is None:
        raise ChatNotFoundError()
    return chat


async def send_external_message(db: AsyncSession, data: WebhookMessageCreate) -> Message:
    scope = CompanyScope(company_id=data.company_id)
    chat = await assert_chat_exists(db, scope, data.chat_id)

    message = Message(
        company_id=chat.company_id,
        chat_id=data.chat_id,
        sender_id=None,
        sender_type="external",
        source_label=data.source_label,
        body=data.body,
    )
    return await _persist_and_publish(db, scope, message)


async def list_messages(
    db: AsyncSession, scope: CompanyScope, caller: Caller, chat_id: uuid.UUID
) -> list[Message]:
    await assert_participant(db, scope, chat_id, caller.id)

    result = await db.scalars(
        scope.select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at)
    )
    return list(result.all())
