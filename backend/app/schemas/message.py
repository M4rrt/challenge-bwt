import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.identity import UserProfile
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
    sender_display_name: str | None
    sender_avatar_url: str | None
    source_label: str | None
    visibility: MessageVisibility
    body: str
    created_at: datetime

    @classmethod
    def of(cls, message: Message, sender: UserProfile | None) -> "MessageRead":
        """The one place a Message becomes a response.

        The REST send, the backlog, the webhook and the live fan-out all send
        this shape, and each used to build it by hand. Adding `visibility` to
        the model broke three of the four at once — which is the cheap version
        of the failure: a field that leaks or goes stale in one of four copies
        breaks nothing loudly at all.

        `sender` has no default, and that is the point. The name is resolved
        from the projection at build time rather than stored on the message, so
        a call site that has no session to resolve it from has to say so out
        loud instead of quietly sending a null — which would read to a client
        exactly like a sender the projection has never heard of.

        None is a real answer twice over: an external sender has no identity to
        project, and a user the projection has never been told about has no name
        here. Neither is a reason to ask the monolith (ADR-0010).
        """
        return cls(
            id=message.id,
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            sender_type=message.sender_type,
            sender_display_name=sender.display_name if sender else None,
            sender_avatar_url=sender.avatar_url if sender else None,
            source_label=message.source_label,
            visibility=message.visibility,
            body=message.body,
            created_at=message.created_at,
        )
