import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.security import get_current_caller
from app.db import get_db
from app.models.message import Message
from app.schemas.message import MessageCreate, MessageRead
from app.services.message import ConversationNotFoundError, list_messages, send_message

router = APIRouter(prefix="/conversations/{conversation_id}/messages", tags=["messages"])


def _to_read(message: Message) -> MessageRead:
    return MessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_type=message.sender_type,
        source_label=message.source_label,
        body=message.body,
        created_at=message.created_at,
    )


@router.post("", response_model=MessageRead, status_code=201)
async def send(
    conversation_id: uuid.UUID,
    data: MessageCreate,
    caller: Caller = Depends(get_current_caller),
    db: AsyncSession = Depends(get_db),
) -> MessageRead:
    try:
        message = await send_message(db, caller, conversation_id, data)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")
    return _to_read(message)


@router.get("", response_model=list[MessageRead])
async def list_all(
    conversation_id: uuid.UUID,
    caller: Caller = Depends(get_current_caller),
    db: AsyncSession = Depends(get_db),
) -> list[MessageRead]:
    try:
        messages = await list_messages(db, caller, conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")
    return [_to_read(m) for m in messages]
