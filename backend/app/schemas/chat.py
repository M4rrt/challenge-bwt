import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.chat import Chat, ChatType, Participant, ParticipantRole
from app.schemas.message import MessageRead


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

    It is `ChatRead` without its two reader-relative fields, and the omission is
    the point. `last_message_at` is the timestamp of the last message *this*
    reader may see; `unread_count` is what sits above *this* reader's watermark.
    A command has no reader to fill either, and answering one with `ChatRead`
    would mean sending a null that cannot be told apart from "nothing has been
    said here" — and a zero that cannot be told apart from "nothing to read".
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
    """A Chat as one reader sees it.

    Two of these fields are reader-relative, and both for the same reason: they
    are computed from what this reader may see and where this reader has got to.
    `ChatComposed` above carries neither, because a command has no reader.

    `unread_count` defaults to zero rather than being optional. A Chat nobody
    has spoken in is a Chat with nothing unread, not a Chat whose count is
    unknown, and a null would leave every client deciding which it meant.

    The read state is here as well as on the response to the request that moved
    it, because "find where I left off" is asked by a client that did not make
    that request — one coming back after a reconnect, or on a second device.
    The count says how much is above the watermark; only these two say where it
    is. Null on both is a real answer and a different one from zero: it is
    somebody who has read nothing here, as against somebody who has read the
    first message.
    """

    id: uuid.UUID
    type: ChatType
    name: str | None
    participant_user_ids: list[uuid.UUID]
    last_message: MessageRead | None = None
    """What was last said here that this reader may read, as the list previews it.

    A third reader-relative field, and the one the other two are read off. Null
    is a Chat nobody has spoken in — which is not the same as a Chat whose last
    message has an empty body: that one is a tombstone, and a tombstone is a
    message.

    The whole response rather than the body alone. A preview that showed text
    and nothing else could not say who spoke, whether it was taken back, or
    whether it came from outside — and each of those would arrive later as
    another field beside this one, describing a message this object already
    holds.
    """
    last_message_at: datetime | None = None
    unread_count: int = 0
    last_read_at: datetime | None = None
    last_read_message_id: uuid.UUID | None = None

    @classmethod
    def of(
        cls,
        chat: Chat,
        last_message: MessageRead | None = None,
        unread_count: int = 0,
        read_by: Participant | None = None,
    ) -> "ChatRead":
        """The one place a Chat becomes a response.

        The list endpoint, the create endpoint and the live chat-list push all
        send this shape. Built at each of them, a field added here reaches two
        of the three and the third goes quietly stale — which is how the
        summary pushed over `/websocket/users/me` would start disagreeing with
        the summary the list returns.

        `last_message_at` is derived here rather than passed in, now that the
        message itself arrives. Taking both would let a caller hand over a
        timestamp belonging to a different message from the one it previews,
        and the two would then disagree in a response nothing else explains.
        """
        return cls(
            id=chat.id,
            type=chat.type,
            name=chat.name,
            participant_user_ids=[p.user_id for p in chat.current_participants],
            last_message=last_message,
            last_message_at=last_message.created_at if last_message else None,
            unread_count=unread_count,
            last_read_at=read_by.last_read_at if read_by else None,
            last_read_message_id=read_by.last_read_message_id if read_by else None,
        )


class ChatPage(BaseModel):
    """One page of a caller's chat list, and where the page after it starts.

    The same shape `MessagePage` settled on in ticket 09, for the same reason:
    the cursor is part of the answer rather than metadata about it, and
    `next_cursor` being null is the only thing that says "there are no more
    Chats". A page that came back short does not say it — a limit and a
    remainder can coincide.

    A bare array had nowhere to put it. That is the whole of why this type
    exists, and why `GET /chats` stopped answering with one.
    """

    chats: list[ChatRead]
    next_cursor: str | None = None
