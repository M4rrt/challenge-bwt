import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.message import Message, MessageVisibility


class MessageCreate(BaseModel):
    body: str
    visibility: MessageVisibility = MessageVisibility.ALL


class WebhookMessageCreate(BaseModel):
    company_id: uuid.UUID
    chat_id: uuid.UUID
    body: str
    source_label: str | None = None


class MessageRead(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    sender_id: uuid.UUID | None
    sender_type: str
    source_label: str | None
    visibility: MessageVisibility
    body: str
    created_at: datetime

    @classmethod
    def of(cls, message: Message) -> "MessageRead":
        """The one place a Message becomes a response.

        The REST send, the backlog, the webhook and the live fan-out all send
        this shape, and each used to build it by hand. Adding `visibility` to
        the model broke three of the four at once — which is the cheap version
        of the failure: a field that leaks or goes stale in one of four copies
        breaks nothing loudly at all.
        """
        return cls(
            id=message.id,
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            sender_type=message.sender_type,
            source_label=message.source_label,
            visibility=message.visibility,
            body=message.body,
            created_at=message.created_at,
        )
