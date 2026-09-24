import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.identity import UserProfile
from app.models.message import Message, MessageVisibility


class MessageCreate(BaseModel):
    """What a Participant sends, including the name their client gave it.

    `client_message_id` has no default, so a send without one is refused at the
    door rather than stored with a null. That is the difference between a client
    that opted out of retry safety and one that forgot the field — and only one
    of those is discovered, later, as a duplicate of something the user said
    once.
    """

    body: str
    client_message_id: str = Field(min_length=1, max_length=64)
    visibility: MessageVisibility = MessageVisibility.ALL


class MessageDelete(BaseModel):
    """Why the author is taking this back, if they care to say.

    Optional because deleting your own typo owes nobody an explanation, and a
    required field would only fill the column with a full stop. What every
    tombstone carries instead is who deleted it, which the service takes from
    the caller rather than from the body.
    """

    reason: str | None = None


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
    client_message_id: str | None
    visibility: MessageVisibility
    body: str
    created_at: datetime
    deleted_at: datetime | None

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

        `deleted_at` is carried through so a deleted Message reads as a marker
        rather than as somebody who said nothing: the empty body is what
        `delete_message` wrote to the row, and this is what makes the
        difference legible. Who deleted it and why stay on the row and out of
        the response — the thread's business is that something was taken back,
        and the rest is for whoever asks afterwards.

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
            client_message_id=message.client_message_id,
            visibility=message.visibility,
            body=message.body,
            created_at=message.created_at,
            deleted_at=message.deleted_at,
        )


class MessagePage(BaseModel):
    """One page of a Chat's history, and where the page before it starts.

    The cursor is in the body rather than a header because it is part of the
    answer, not metadata about it: without it the response does not say whether
    there is more thread above. `next_cursor` being null is what "you have
    reached the beginning" means, and it is the only thing that says so.

    A bare array had nowhere to put it. That is the whole of why this type
    exists — a page of messages is not a list of messages, it is a list of
    messages and a position.
    """

    messages: list[MessageRead]
    next_cursor: str | None = None
