import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, ConversationParticipant
from app.models.user import User
from app.schemas.conversation import ConversationCreate


class GroupNameRequiredError(Exception):
    pass


async def _find_existing_one_to_one(
    db: AsyncSession, participant_ids: set[uuid.UUID]
) -> Conversation | None:
    matching_conversation_ids = (
        select(ConversationParticipant.conversation_id)
        .where(ConversationParticipant.user_id.in_(participant_ids))
        .group_by(ConversationParticipant.conversation_id)
        .having(func.count(ConversationParticipant.user_id) == len(participant_ids))
        .subquery()
    )
    conversation_id = await db.scalar(
        select(ConversationParticipant.conversation_id)
        .where(ConversationParticipant.conversation_id.in_(select(matching_conversation_ids)))
        .group_by(ConversationParticipant.conversation_id)
        .having(func.count(ConversationParticipant.user_id) == len(participant_ids))
    )
    if conversation_id is None:
        return None
    return await db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.participants))
    )


async def create_conversation(
    db: AsyncSession, current_user: User, data: ConversationCreate
) -> Conversation:
    participant_ids = {current_user.id, *data.participant_user_ids}

    if len(participant_ids) > 2 and not data.name:
        raise GroupNameRequiredError()

    if len(participant_ids) == 2:
        existing = await _find_existing_one_to_one(db, participant_ids)
        if existing is not None:
            return existing

    conversation = Conversation(name=data.name)
    conversation.participants = [
        ConversationParticipant(user_id=user_id) for user_id in participant_ids
    ]
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation, attribute_names=["participants"])
    return conversation


async def list_conversations(db: AsyncSession, current_user: User) -> list[Conversation]:
    result = await db.scalars(
        select(Conversation)
        .join(ConversationParticipant)
        .where(ConversationParticipant.user_id == current_user.id)
        .options(selectinload(Conversation.participants))
    )
    return list(result.all())
