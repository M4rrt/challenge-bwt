import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.security import get_company_scope, get_current_caller
from app.db import get_db
from app.schemas.message import MessageCreate, MessageDelete, MessageRead
from app.services.chat import ChatNotFoundError
from app.services.message import (
    MessageNotFoundError,
    NotTheAuthorError,
    VisibilityNotAllowedError,
    delete_message,
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
        return await send_message(db, scope, caller, chat_id, data)
    except ChatNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    except VisibilityNotAllowedError as refused:
        raise HTTPException(status_code=422, detail=refused.detail)


@router.delete("/{message_id}", response_model=MessageRead)
async def delete(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    data: MessageDelete = Body(default_factory=MessageDelete),
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> MessageRead:
    """The tombstone comes back, rather than a bare 204.

    The body is built per request rather than defaulted to one shared instance
    made at import, which is the ordinary reason: a default that every caller
    is handed the same copy of is a default waiting to be written through.

    The caller has to show the marker in place of what they were showing, and
    it is the same shape everyone else receives over the fan-out — so there is
    one description of a deleted Message and not two.
    """
    try:
        return await delete_message(db, scope, caller, chat_id, message_id, data)
    except ChatNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    except MessageNotFoundError as missing:
        raise HTTPException(status_code=404, detail=missing.detail)
    except NotTheAuthorError as refused:
        raise HTTPException(status_code=403, detail=refused.detail)


@router.get("", response_model=list[MessageRead])
async def list_all(
    chat_id: uuid.UUID,
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> list[MessageRead]:
    try:
        return await list_messages(db, scope, caller, chat_id)
    except ChatNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
