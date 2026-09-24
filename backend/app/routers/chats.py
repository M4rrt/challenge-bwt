import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.cursor import InvalidCursorError
from app.core.security import get_company_scope, get_current_caller
from app.db import get_db
from app.schemas.chat import ChatPage
from app.schemas.read_state import MarkRead, ReadState
from app.services.chat import (
    DEFAULT_CHAT_PAGE_LIMIT,
    MAX_CHAT_PAGE_LIMIT,
    ChatNotFoundError,
    list_chats,
)
from app.services.message import MessageNotFoundError
from app.services.read_state import mark_read

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("", response_model=ChatPage)
async def list_all(
    search: str | None = Query(
        default=None,
        max_length=100,
        description="part of a participant's name, or of the chat's own name",
    ),
    before: str | None = Query(
        default=None, description="a next_cursor from an earlier page"
    ),
    limit: int = Query(default=DEFAULT_CHAT_PAGE_LIMIT, ge=1, le=MAX_CHAT_PAGE_LIMIT),
    caller: Caller = Depends(get_current_caller),
    scope: CompanyScope = Depends(get_company_scope),
    db: AsyncSession = Depends(get_db),
) -> ChatPage:
    """The caller's Chats by last activity, a page at a time.

    A cursor this service did not issue is refused rather than ignored, which
    is the same choice `GET /chats/{id}/messages` makes: ignoring it would
    answer a corrupted scroll position with the top of the list and say nothing
    about it, and a client cannot tell that from having started over.

    `search` is bounded because it becomes a `LIKE` pattern. Nobody types a
    hundred characters to find a colleague, and an unbounded one is a pattern
    the database is asked to walk every profile with.
    """
    try:
        return await list_chats(
            db, scope, caller, search=search, before=before, limit=limit
        )
    except InvalidCursorError as broken:
        raise HTTPException(status_code=422, detail=broken.detail)


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
