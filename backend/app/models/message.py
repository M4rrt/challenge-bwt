import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
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

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id"))
    sender_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    sender_type: Mapped[str] = mapped_column(String)
    source_label: Mapped[str | None] = mapped_column(String, nullable=True)
    visibility: Mapped[MessageVisibility] = mapped_column(
        stored_by_value(MessageVisibility, "message_visibility")
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
