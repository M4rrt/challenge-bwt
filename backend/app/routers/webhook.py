from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_webhook_signature
from app.db import get_db
from app.schemas.message import MessageRead, WebhookMessageCreate
from app.services.message import ChatNotFoundError, send_external_message

router = APIRouter(prefix="/webhook", tags=["webhook"])


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
    except ChatNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    return MessageRead.of(message)
