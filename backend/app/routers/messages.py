import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.security import get_company_scope, get_current_caller
from app.db import get_db
from app.schemas.message import MessageCreate, MessageRead
from app.services.message import (
    ChatNotFoundError,
    VisibilityNotAllowedError,
    list_messages,
    send_message,
)

router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["messages"])


@router.post("", response_model=MessageRead, status_code=201)
async def send(
    chat_id: uuid.UUID,
    data: MessageCreate,
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> MessageRead:
    try:
        message = await send_message(db, scope, caller, chat_id, data)
    except ChatNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    except VisibilityNotAllowedError as refused:
        raise HTTPException(status_code=422, detail=refused.detail)
    return MessageRead.of(message)


@router.get("", response_model=list[MessageRead])
async def list_all(
    chat_id: uuid.UUID,
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> list[MessageRead]:
    try:
        messages = await list_messages(db, scope, caller, chat_id)
    except ChatNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    return [MessageRead.of(m) for m in messages]
