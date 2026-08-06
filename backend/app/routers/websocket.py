import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_user_from_token
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
    user = await decode_user_from_token(token, db)
    if user is None:
        await websocket.close(code=1008)
        return

    try:
        await assert_participant(db, conversation_id, user.id)
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
