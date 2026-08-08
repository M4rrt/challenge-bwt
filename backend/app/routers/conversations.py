from datetime import datetime, timezone

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
    get_last_message_at_by_conversation,
    list_conversations,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])

_UNIX_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


def _to_read(conversation: Conversation, last_message_at: datetime | None = None) -> ConversationRead:
    return ConversationRead(
        id=conversation.id,
        name=conversation.name,
        participant_user_ids=[p.user_id for p in conversation.participants],
        last_message_at=last_message_at,
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
    last_message_at_by_id = await get_last_message_at_by_conversation(db, [conversation.id])
    return _to_read(conversation, last_message_at_by_id.get(conversation.id))


@router.get("", response_model=list[ConversationRead])
async def list_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationRead]:
    conversations = await list_conversations(db, current_user)
    last_message_at_by_id = await get_last_message_at_by_conversation(
        db, [c.id for c in conversations]
    )
    conversations.sort(key=lambda c: last_message_at_by_id.get(c.id, _UNIX_EPOCH), reverse=True)
    return [_to_read(c, last_message_at_by_id.get(c.id)) for c in conversations]
