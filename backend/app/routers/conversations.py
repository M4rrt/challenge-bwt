from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models.user import User
from app.models.conversation import Conversation
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.services.conversation import (
    GroupNameRequiredError,
    create_conversation,
    list_conversations,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _to_read(conversation: Conversation) -> ConversationRead:
    return ConversationRead(
        id=conversation.id,
        name=conversation.name,
        participant_user_ids=[p.user_id for p in conversation.participants],
    )


@router.post("", response_model=ConversationRead, status_code=201)
async def create(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    try:
        conversation = await create_conversation(db, current_user, data)
    except GroupNameRequiredError:
        raise HTTPException(status_code=422, detail="name is required for group conversations")
    return _to_read(conversation)


@router.get("", response_model=list[ConversationRead])
async def list_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationRead]:
    conversations = await list_conversations(db, current_user)
    return [_to_read(c) for c in conversations]
