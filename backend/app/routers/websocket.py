import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import verify_chat_token
from app.core.company_scope import CompanyScope
from app.db import get_db
from app.services.message import ConversationNotFoundError, assert_participant
from app.services.realtime import connection_manager

router = APIRouter(prefix="/websocket", tags=["websocket"])


@router.websocket("/conversations/{conversation_id}")
async def conversation_socket(
    websocket: WebSocket,
    conversation_id: uuid.UUID,
    token: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    caller = verify_chat_token(token)
    if caller is None:
        await websocket.close(code=1008)
        return

    try:
        await assert_participant(db, CompanyScope.of(caller), conversation_id, caller.id)
    except ConversationNotFoundError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    connection_manager.connect(conversation_id, websocket)
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
        connection_manager.disconnect(conversation_id, websocket)


@router.websocket("/users/me")
async def user_socket(websocket: WebSocket, token: str) -> None:
    caller = verify_chat_token(token)
    if caller is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    connection_manager.connect_user(caller.company_id, caller.id, websocket)
    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect_user(caller.company_id, caller.id, websocket)
