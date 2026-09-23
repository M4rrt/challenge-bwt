from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.security import get_company_scope, get_current_caller
from app.db import get_db
from app.schemas.chat import ChatCreate, ChatRead
from app.services.chat import (
    ChatShapeError,
    create_chat,
    get_last_message_at_by_chat,
    list_chats,
)

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatRead, status_code=201)
async def create(
    data: ChatCreate,
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> ChatRead:
    try:
        chat = await create_chat(db, scope, caller, data)
    except ChatShapeError as refused:
        raise HTTPException(status_code=422, detail=refused.detail)
    last_message_at = await get_last_message_at_by_chat(db, scope, [chat.id])
    return ChatRead.of(chat, last_message_at.get(chat.id))


@router.get("", response_model=list[ChatRead])
async def list_all(
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> list[ChatRead]:
    return await list_chats(db, scope, caller)
