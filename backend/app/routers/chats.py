import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.security import get_company_scope, get_current_caller
from app.db import get_db
from app.schemas.chat import ChatRead
from app.schemas.read_state import MarkRead, ReadState
from app.services.chat import ChatNotFoundError, list_chats
from app.services.message import MessageNotFoundError
from app.services.read_state import mark_read

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("", response_model=list[ChatRead])
async def list_all(
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> list[ChatRead]:
    return await list_chats(db, scope, caller)


@router.post("/{chat_id}/read", response_model=ReadState)
async def mark_as_read(
    chat_id: uuid.UUID,
    data: MarkRead,
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> ReadState:
    """Move the caller's watermark, and answer with where it actually landed.

    Where it landed is not always where the request asked: the timestamp is
    clamped, and the watermark does not move backwards. Answering with the
    stored state rather than an empty 204 is what lets a client show a count
    that agrees with the one the service will compute.
    """
    try:
        return await mark_read(db, scope, caller, chat_id, data)
    except ChatNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    except MessageNotFoundError as missing:
        raise HTTPException(status_code=404, detail=missing.detail)
