import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageCreate(BaseModel):
    body: str


class WebhookMessageCreate(BaseModel):
    conversation_id: uuid.UUID
    body: str
    source_label: str | None = None


class MessageRead(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID | None
    sender_type: str
    source_label: str | None
    body: str
    created_at: datetime
