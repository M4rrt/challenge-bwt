import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.company_scope import CompanyScoped
from app.db import Base, stored_by_value


class MessageVisibility(StrEnum):
    """Who a Message is addressed to inside its Chat.

    Only two values, and the second one is only legal in a Client Chat: in a
    Staff Chat everyone is already staff, so the distinction says nothing and
    the service refuses it rather than storing a row whose meaning depends on
    a rule nobody applied.
    """

    ALL = "all"
    STAFF_ONLY = "staff_only"


class Message(Base, CompanyScoped):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "sender_id",
            "client_message_id",
            name="uq_messages_sender_client_message_id",
        ),
        # The pair the cursor pages on, with the Chat it pages within. Declared
        # here as well as in the migration, because a model that does not carry
        # its own indexes makes every future autogenerate propose dropping them.
        Index(
            "ix_messages_chat_id_created_at_id",
            "chat_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id"))
    sender_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    sender_type: Mapped[str] = mapped_column(String)
    source_label: Mapped[str | None] = mapped_column(String, nullable=True)
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """What the sender's client called this message before the service had a name for it.

    Null means nobody supplied one: a Message with no sender has no client to
    have generated it, and rows predating the column were written before there
    was a field to send. Every Participant's send carries one, refused at the
    door if it does not — see the constraint above, which is where "the same id
    twice from the same sender in the same Chat is the same message" lives.
    """
    visibility: Mapped[MessageVisibility] = mapped_column(
        stored_by_value(MessageVisibility, "message_visibility")
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """When this Message was taken back, or null if it was not.

    The three deletion columns are one fact in three parts, and this is the one
    that decides it: `deleted_at` is what every reader checks, and the other two
    say nothing on their own. Deleting clears `body` rather than removing the
    row, because the uniqueness constraint and the cursor both rest on the row
    still being there — see the migration `c6b4e2a9d813`.
    """
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


OLDEST_FIRST = (Message.created_at, Message.id)
"""The total order a Chat's messages are read in, spelled once.

`created_at` alone is a partial order: two messages the clock cannot separate
share an instant, and their relative order is then whatever the plan happens to
produce — which can differ between two reads of the same rows.

That is not merely untidy, because the cursor pages over exactly this order. A
pair that sorts one way on one page and the other way on the next is a message
skipped or a message served twice. The identifier is the tiebreaker: arbitrary,
since a v4 uuid says nothing about time, but total and stable, which is the
whole of what a cursor needs. Every read of a Chat's history orders by this
tuple, so the ordering and the cursor cannot come to disagree.

It lives beside the table rather than in `services/message.py`, where ticket 09
first wrote it, because the chat list reaches for it too: the last message of
each Chat is the newest row in this same order, and `services/chat.py` is
underneath `services/message.py` in the import graph. Two orderings, one per
service, is the drift the tiebreaker exists to prevent.
"""

NEWEST_FIRST = tuple(column.desc() for column in OLDEST_FIRST)
"""The same order, walked from the end — which is where a chat is read from.

A thread opens on what was said last, so the page has to be found by walking
backwards, and so does the one row the chat list previews. Derived from
`OLDEST_FIRST` rather than written out, because the two directions disagreeing
on the tiebreaker is exactly the bug the tiebreaker was added to prevent.
"""
