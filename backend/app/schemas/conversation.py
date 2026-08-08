import uuid
from datetime import datetime

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    participant_user_ids: list[uuid.UUID]
    name: str | None = None


class ConversationRead(BaseModel):
    id: uuid.UUID
    name: str | None
    participant_user_ids: list[uuid.UUID]
    last_message_at: datetime | None = None
