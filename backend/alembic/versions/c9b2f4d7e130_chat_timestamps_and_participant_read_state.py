"""Chat timestamps, and the Participant's read state and departure

Revision ID: c9b2f4d7e130
Revises: b7e1d0c4a92f
Create Date: 2026-09-23

`left_at` is what makes leaving a Chat survivable. Deleting the Participant
row would take the read state with it and leave the messages that user sent
attributable to nobody, so departure is recorded as the moment it happened and
every read of "who is in this Chat" asks for the rows with no such moment.

`last_read_at` and `last_read_message_id` have no reader until ticket 09. They
are added now because they belong to the Participant as the spec describes it,
and because adding a column to an empty table is not the same operation as
adding one to a table with traffic in it.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9b2f4d7e130"
down_revision = "b7e1d0c4a92f"
branch_labels = None
depends_on = None


def _stamped(column: str) -> sa.Column:
    return sa.Column(
        column,
        sa.DateTime(timezone=True),
        server_default=sa.func.clock_timestamp(),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column("chats", _stamped("created_at"))
    op.add_column("chats", _stamped("updated_at"))
    op.add_column("participants", _stamped("joined_at"))
    op.add_column(
        "participants", sa.Column("left_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "participants", sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "participants", sa.Column("last_read_message_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "participants_last_read_message_id_fkey",
        "participants",
        "messages",
        ["last_read_message_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "participants_last_read_message_id_fkey", "participants", type_="foreignkey"
    )
    for column in ("last_read_message_id", "last_read_at", "left_at", "joined_at"):
        op.drop_column("participants", column)
    for column in ("updated_at", "created_at"):
        op.drop_column("chats", column)
