from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_webhook_signature
from app.db import get_db
from app.models.message import Message
from app.schemas.message import MessageRead, WebhookMessageCreate
from app.services.message import ConversationNotFoundError, send_external_message

router = APIRouter(prefix="/webhook", tags=["webhook"])


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


@router.post("/messages", response_model=MessageRead, status_code=201)
async def receive(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageRead:
    body = await request.body()
    if not verify_webhook_signature(body, request.headers.get("X-Signature")):
        raise HTTPException(status_code=401, detail="invalid signature")

    data = WebhookMessageCreate.model_validate_json(body)
    try:
        message = await send_external_message(db, data)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")
    return _to_read(message)
