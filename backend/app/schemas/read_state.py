"""What a Participant has read in a Chat, on the wire in both directions."""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.chat import Participant


class MarkRead(BaseModel):
    """How far the caller has read, as their own client understands it.

    `read_at` comes from the caller because only the caller knows when they
    looked — and that is exactly why it is clamped on the way in: a device
    whose clock runs fast would otherwise mark as read every message that
    arrives for as long as the skew lasts, and the Chat's unread state would
    simply never come back.

    `message_id` is optional because the two halves answer different questions.
    The timestamp is what the unread count is computed from and a client always
    has one; the message is where a client re-anchors its scroll, and a caller
    who has read an empty Chat has no message to name.
    """

    read_at: datetime
    message_id: uuid.UUID | None = None

    @field_validator("read_at")
    @classmethod
    def _must_name_an_instant(cls, read_at: datetime) -> datetime:
        """A timestamp with no zone names no instant, so it cannot be clamped.

        The same argument the cursor makes. Refused at the door rather than
        guessed at: read as UTC it would be wrong by the caller's offset, and
        read as local time it would be wrong by the server's. Both are silent,
        and both land in a column whose whole job is to be compared against
        other instants.
        """
        if read_at.tzinfo is None:
            raise ValueError("read_at must carry a timezone")
        return read_at


class ReadState(BaseModel):
    """The watermark as it now stands, sent back rather than assumed.

    The request says where the caller thinks they got to and the response says
    where they actually are, which are not always the same: the clamp and the
    refusal to move backwards both change the answer. A client that assumed its
    own request had been stored verbatim would show an unread count the service
    does not agree with.
    """

    last_read_at: datetime | None
    last_read_message_id: uuid.UUID | None

    @classmethod
    def of(cls, participant: Participant) -> "ReadState":
        return cls(
            last_read_at=participant.last_read_at,
            last_read_message_id=participant.last_read_message_id,
        )
