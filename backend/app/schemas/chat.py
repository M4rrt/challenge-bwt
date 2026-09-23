import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.chat import Chat, ChatType, ParticipantRole


class ParticipantIdentity(BaseModel):
    """One Participant as the command carries them, already validated.

    The whole identity travels with the identifier because the service holds no
    user table to look anything up in and ADR-0010 forbids asking back. The
    monolith had this data in hand to validate the composition, so sending it
    along costs nothing and removes the one case that would force a call in the
    other direction.

    `user_kind` is what the Chat's shape is validated against, and typing it as
    the role refuses a kind the service's two words cannot express. The display
    name and avatar are the identity projection's first write (ticket 06); the
    contract is fixed here so that landing the projection does not move the wire
    shape under the monolith.
    """

    user_id: uuid.UUID
    company_id: uuid.UUID
    user_kind: ParticipantRole
    display_name: str
    avatar_url: str | None = None


class ChatCommand(BaseModel):
    """Create this Chat, with these people in it."""

    type: ChatType
    participants: list[ParticipantIdentity]
    name: str | None = None


class AddParticipantCommand(BaseModel):
    """Put this person into that Chat.

    The name travels with it because adding a third person turns a 1:1 into a
    group, and a group carries a name. Sending both at once is one act of
    composition; refusing and waiting for a rename would be two.
    """

    participant: ParticipantIdentity
    name: str | None = None


class ChatComposed(BaseModel):
    """A Chat as a command leaves it: what now exists, with no reader in the picture.

    It is `ChatRead` without `last_message_at`, and the omission is the point. That
    field is reader-relative — it is the timestamp of the last message *this*
    reader may see — and a command has no reader whose visibility could fill it.
    Answering a command with `ChatRead` would mean sending a null that cannot be
    told apart from "nothing has been said here".
    """

    id: uuid.UUID
    type: ChatType
    name: str | None
    participant_user_ids: list[uuid.UUID]

    @classmethod
    def of(cls, chat: Chat) -> "ChatComposed":
        return cls(
            id=chat.id,
            type=chat.type,
            name=chat.name,
            participant_user_ids=[p.user_id for p in chat.current_participants],
        )


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
