import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.company_scope import CompanyScoped
from app.db import Base


class OutboxEvent(Base, CompanyScoped):
    """Something to be delivered, written in the transaction that made it true.

    Realtime delivery used to happen inside the request, between the commit and
    the response. That bought two silent failures at once: a transaction that
    rolled back after publishing had already told people about a message the
    database no longer held, and a process that died between commit and publish
    lost the delivery with nothing recording that it owed one.

    A row here is the record of that debt. It is written in the same
    transaction as the Message it announces — so a rollback takes the
    announcement with it — and a separate drain pays it afterwards.

    `address` is where it goes, and it is the whole of the routing decision.
    Who may see this payload was settled when the row was written; the drain
    reads no rule and applies no filter, which is what keeps a future emitter
    from forgetting one.
    """

    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    address: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
