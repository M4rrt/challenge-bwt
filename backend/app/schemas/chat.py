import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.chat import Chat, ChatType, ParticipantRole


class ParticipantCreate(BaseModel):
    """One Participant as the caller names them.

    The user kind travels with the identifier because the service holds no user
    table to look it up in, and it is what the Chat's shape is validated
    against.
    """

    user_id: uuid.UUID
    user_kind: ParticipantRole


class ChatCreate(BaseModel):
    type: ChatType
    participants: list[ParticipantCreate]
    name: str | None = None


class ChatRead(BaseModel):
    id: uuid.UUID
    type: ChatType
    name: str | None
    participant_user_ids: list[uuid.UUID]
    last_message_at: datetime | None = None

    @classmethod
    def of(cls, chat: Chat, last_message_at: datetime | None = None) -> "ChatRead":
        """The one place a Chat becomes a response.

        The list endpoint, the create endpoint and the live chat-list push all
        send this shape. Built at each of them, a field added here reaches two
        of the three and the third goes quietly stale — which is how the
        summary pushed over `/websocket/users/me` would start disagreeing with
        the summary the list returns.
        """
        return cls(
            id=chat.id,
            type=chat.type,
            name=chat.name,
            participant_user_ids=[p.user_id for p in chat.current_participants],
            last_message_at=last_message_at,
        )
