"""a Message carries its visibility

Revision ID: d2e5a81c6f47
Revises: c9b2f4d7e130
Create Date: 2026-09-23

A Message is addressed either to everyone in its Chat or only to the Company's
staff in it. Which one it is has to be on the row: it is decided once, by the
sender, and every later read answers from it rather than re-deriving it from
who happens to be a Participant now.

Rows written before this migration were all ordinary messages — there was no
other kind to write — so the backfill is not a guess, and the default is
dropped afterwards so that the value is always something a writer chose.

The column is VARCHAR with a CHECK rather than a PostgreSQL enum type, for the
reason `b7e1d0c4a92f` gives: adding a value later stays an ordinary constraint
change instead of an `ALTER TYPE` that cannot run inside a transaction.
"""

import sqlalchemy as sa
from alembic import op

revision = "d2e5a81c6f47"
down_revision = "c9b2f4d7e130"
branch_labels = None
depends_on = None

_MESSAGE_VISIBILITY = sa.Enum(
    "all", "staff_only", native_enum=False, create_constraint=True, name="message_visibility"
)


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("visibility", _MESSAGE_VISIBILITY, nullable=False, server_default="all"),
    )
    op.alter_column("messages", "visibility", server_default=None)


def downgrade() -> None:
    op.drop_column("messages", "visibility")
