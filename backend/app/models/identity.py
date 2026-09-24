import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.company_scope import CompanyScoped
from app.db import Base


class UserProfile(Base, CompanyScoped):
    """What the service knows about a user, so that it never has to ask.

    ADR-0010 forbids a request path that calls the monolith, and a display name
    is needed on every message response — so the name has to already be here
    when the response is built. This row is where it is.

    Keyed by (Company, user) rather than by user alone. The same user id can
    exist in two Companies, which every fan-out address already carries for
    exactly that reason, and two Companies may well describe the same person
    differently.

    `user_kind` is a plain string with no check constraint behind it, unlike
    every other enumerated column in this schema. Those are the service's own
    vocabulary and it refuses what it cannot express; this one mirrors the
    monolith's, which is wider than two words, and a projection that refuses to
    record what its source says is not a projection.

    Nothing reads it yet. The visibility rule takes the reader's kind from the
    token (`core/message_visibility.py`), never from here, so this column
    denies nobody anything — say so rather than implying otherwise, because a
    column believed to be load-bearing is one somebody will build on. It is
    here because the projection's job is to hold what the monolith says about a
    user, and a chat list that shows who it is talking to (ticket 10) and
    supervised reading (ticket 13) are what plausibly read it first.
    """

    __tablename__ = "user_profiles"
    __table_args__ = (UniqueConstraint("company_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    user_kind: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """When the monolith last changed this identity, by the monolith's clock.

    Null means nobody has said: the row was created by a composition command,
    which carries an identity but no timestamp for it (`ParticipantIdentity` is
    the wire shape ticket 05 fixed). A null therefore loses every comparison in
    `apply`, which is the honest reading — an identity of unknown age is the
    oldest thing there is, and must never overwrite something dated.
    """
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    """When this service last wrote the row, by this service's clock.

    No `onupdate` here, deliberately. Every write to this table is a Core
    upsert, and `onupdate` fires only for ORM updates — it would be dead
    configuration that reads as a guarantee, and the first person to trust it
    would ship a projection whose lag metric never moves. `apply_identities`
    sets this column explicitly instead.

    Its distance from `source_updated_at` is the projection's lag, which is the
    one health signal this projection has: there is no cache hit rate, because
    there is no miss path.
    """


# What the chat list's name filter walks, declared here as well as in the
# migration `f2b7d419ac53` for the reason the messages index gives: a model that
# does not carry its own indexes makes every future autogenerate propose
# dropping them.
#
# It sits outside `__table_args__` because that tuple is built while the class
# body is still running, before `display_name` exists to be wrapped. Naming the
# column here associates the index with the table all the same, which is what
# puts it in `Base.metadata`.
#
# The expression has to be spelled exactly as `_unaccented` spells it in
# `services/chat.py` — an index on a different expression is an index the
# planner silently declines to use.
#
# The label exists only to give `postgresql_ops` something to key on. An
# unlabelled expression has no key, so the operator class is silently dropped
# and the model ends up declaring a GIN index with no opclass — not the index
# the migration builds, and one Postgres would refuse outright. Written inline
# in the expression instead, Alembic cannot parse the element and skips the
# comparison with a warning, passing `alembic check` by declining to look. The
# label itself is not emitted in the DDL.
Index(
    "ix_user_profiles_display_name_unaccented",
    func.immutable_unaccent(UserProfile.display_name).label("unaccented_display_name"),
    postgresql_using="gin",
    postgresql_ops={"unaccented_display_name": "gin_trgm_ops"},
)
