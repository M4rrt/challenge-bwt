import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import verify_chat_token
from app.core.company_scope import CompanyScope
from app.core.message_visibility import may_read
from app.db import get_db
from app.models.message import MessageVisibility
from app.services.message import ChatNotFoundError, chat_of_participant
from app.services.realtime import (
    address_for_chat,
    address_for_chat_staff,
    address_for_user,
    connection_manager,
)

router = APIRouter(prefix="/websocket", tags=["websocket"])


@router.websocket("/chats/{chat_id}")
async def chat_socket(
    websocket: WebSocket,
    chat_id: uuid.UUID,
    token: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    caller = verify_chat_token(token)
    if caller is None:
        await websocket.close(code=1008)
        return

    try:
        chat = await chat_of_participant(db, CompanyScope.of(caller), chat_id, caller.id)
    except ChatNotFoundError:
        await websocket.close(code=1008)
        return

    # The staff address is joined here or not at all. Entitlement is decided
    # once, at the handshake, by the same predicate the API asks — so there is
    # no per-frame filter for a future emitter to forget.
    addresses = [address_for_chat(caller.company_id, chat_id)]
    if may_read(
        reader_kind=caller.user_kind,
        reader_company_id=caller.company_id,
        chat_company_id=chat.company_id,
        chat_type=chat.type,
        visibility=MessageVisibility.STAFF_ONLY,
    ):
        addresses.append(address_for_chat_staff(caller.company_id, chat_id))

    await websocket.accept()
    connection_manager.connect(addresses, websocket)
    try:
        while True:
            raw = await websocket.receive_json()
            message_type = raw.get("type")
            match message_type:
                case _:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(addresses, websocket)


@router.websocket("/users/me")
async def user_socket(websocket: WebSocket, token: str) -> None:
    caller = verify_chat_token(token)
    if caller is None:
        await websocket.close(code=1008)
        return

    addresses = [address_for_user(caller.company_id, caller.id)]
    await websocket.accept()
    connection_manager.connect(addresses, websocket)
    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(addresses, websocket)
