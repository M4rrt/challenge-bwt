import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.services.realtime import publish_to_user


class GroupNameRequiredError(Exception):
    pass


async def _find_existing_one_to_one(
    db: AsyncSession, scope: CompanyScope, participant_ids: set[uuid.UUID]
) -> Conversation | None:
    chats_with_these_participants = (
        scope.select(ConversationParticipant)
        .with_only_columns(ConversationParticipant.conversation_id)
        .where(ConversationParticipant.user_id.in_(participant_ids))
        .group_by(ConversationParticipant.conversation_id)
        .having(func.count(ConversationParticipant.user_id) == len(participant_ids))
        .subquery()
    )
    conversation_id = await db.scalar(
        scope.select(ConversationParticipant)
        .with_only_columns(ConversationParticipant.conversation_id)
        .where(ConversationParticipant.conversation_id.in_(select(chats_with_these_participants)))
        .group_by(ConversationParticipant.conversation_id)
        .having(func.count(ConversationParticipant.user_id) == len(participant_ids))
    )
    if conversation_id is None:
        return None
    return await db.scalar(
        scope.select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.participants))
    )


async def create_conversation(
    db: AsyncSession, scope: CompanyScope, caller: Caller, data: ConversationCreate
) -> Conversation:
    participant_ids = {caller.id, *data.participant_user_ids}

    if len(participant_ids) > 2 and not data.name:
        raise GroupNameRequiredError()

    if len(participant_ids) == 2:
        existing = await _find_existing_one_to_one(db, scope, participant_ids)
        if existing is not None:
            return existing

    conversation = Conversation(company_id=scope.company_id, name=data.name)
    conversation.participants = [
        ConversationParticipant(company_id=scope.company_id, user_id=user_id)
        for user_id in participant_ids
    ]
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation, attribute_names=["participants"])
    await notify_participants(db, scope, conversation.id)
    return conversation


async def list_conversations(
    db: AsyncSession, scope: CompanyScope, caller: Caller
) -> list[Conversation]:
    result = await db.scalars(
        scope.select(Conversation)
        .join(ConversationParticipant)
        .where(ConversationParticipant.user_id == caller.id)
        .options(selectinload(Conversation.participants))
    )
    return list(result.all())


async def get_last_message_at_by_conversation(
    db: AsyncSession, scope: CompanyScope, conversation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    if not conversation_ids:
        return {}
    result = await db.execute(
        scope.select(Message)
        .with_only_columns(Message.conversation_id, func.max(Message.created_at))
        .where(Message.conversation_id.in_(conversation_ids))
        .group_by(Message.conversation_id)
    )
    return dict(result.all())


async def notify_participants(
    db: AsyncSession, scope: CompanyScope, conversation_id: uuid.UUID
) -> None:
    conversation = await db.scalar(
        scope.select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.participants))
    )
    if conversation is None:
        return

    last_message_at_by_id = await get_last_message_at_by_conversation(db, scope, [conversation_id])
    payload = ConversationRead(
        id=conversation.id,
        name=conversation.name,
        participant_user_ids=[p.user_id for p in conversation.participants],
        last_message_at=last_message_at_by_id.get(conversation_id),
    ).model_dump_json()

    for participant in conversation.participants:
        await publish_to_user(scope.company_id, participant.user_id, payload)
