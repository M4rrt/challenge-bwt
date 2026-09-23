import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.company_scope import CompanyScoped
from app.db import Base


class ChatType(StrEnum):
    """Which of the two shapes a Chat has, and therefore which rules apply to it."""

    STAFF = "staff"
    CLIENT = "client"


class ParticipantRole(StrEnum):
    """What a Participant is inside the Chat, mirrored from the token's user kind."""

    STAFF = "staff"
    CLIENT = "client"


def _stored_by_value(enum: type[StrEnum], name: str) -> Enum:
    """A VARCHAR column holding the enum's values, checked in the database.

    Two defaults have to be overridden together. SQLAlchemy stores a Python
    enum by member *name*, so `ChatType.STAFF` would land as `STAFF` while
    every migration, payload and log says `staff` — invisible until something
    reads the column without going through the mapper. And `create_constraint`
    is off by default, which leaves the set of legal values as a claim the
    schema does not make.
    """
    return Enum(
        enum,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
        name=name,
    )


class Chat(Base, CompanyScoped):
    """A container for messages between a set of Participants.

    1:1 and group are the same thing here: a 1:1 is a Chat with exactly two
    Participants, not a separate entity with its own table and its own rules.
    """

    __tablename__ = "chats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    type: Mapped[ChatType] = mapped_column(_stored_by_value(ChatType, "chat_type"))
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
    )

    participants: Mapped[list["Participant"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Participant.user_id",
    )

    @property
    def current_participants(self) -> list["Participant"]:
        """Who is in the Chat now, as opposed to who has ever been in it.

        The relationship deliberately still loads everyone, because a message
        sent by somebody who has since left is not an orphan and tickets 09 and
        13 have to be able to reach their row. What a response shows is this.
        """
        return [participant for participant in self.participants if participant.left_at is None]


class Participant(Base, CompanyScoped):
    """The link between a user and a Chat, carrying their read state in it.

    Leaving is recorded as the moment it happened rather than by deleting the
    row: the messages this user sent stay attributable, and a Chat they were
    once in stays explicable. `left_at` being null is what "still here" means.
    """

    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("chat_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    role: Mapped[ParticipantRole] = mapped_column(
        _stored_by_value(ParticipantRole, "participant_role")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_read_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True
    )

    chat: Mapped["Chat"] = relationship(back_populates="participants")


STILL_IN_THE_CHAT = Participant.left_at.is_(None)
"""The one spelling of "is a current Participant" in a query.

Leaving is recorded rather than deleted, so every read that means "who is in
this Chat" has to say so — and a read that forgets shows a Chat to somebody who
walked out of it.
"""
