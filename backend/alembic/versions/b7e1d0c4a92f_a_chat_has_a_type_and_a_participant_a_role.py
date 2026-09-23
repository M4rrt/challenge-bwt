"""a Chat has a type and a Participant a role

Revision ID: b7e1d0c4a92f
Revises: a3f7c2e51b08
Create Date: 2026-09-23

A Chat is a Staff Chat or a Client Chat, and which one it is decides what may
be written into it — so the answer belongs on the row rather than being
recomputed from whoever happens to be a Participant right now. A Participant's
role is the user kind the monolith vouched for at the moment they were added.

Rows written before this migration have neither. Nothing distinguishes a Staff
Chat from a Client Chat among them, because the distinction did not exist while
they were written, and a guessed type is a validation rule quietly evaluated
against a made-up input. They are deleted instead, for the reason
`c1d4a7e90f32` gives for the same act: this service has not been in production
and the rows it drops are development fixtures.

The columns are VARCHAR with a CHECK rather than a PostgreSQL enum type, so
adding a value later is an ordinary constraint change rather than an
`ALTER TYPE` that cannot run inside a transaction.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7e1d0c4a92f"
down_revision = "a3f7c2e51b08"
branch_labels = None
depends_on = None

_CHAT_TYPE = sa.Enum(
    "staff", "client", native_enum=False, create_constraint=True, name="chat_type"
)
_PARTICIPANT_ROLE = sa.Enum(
    "staff", "client", native_enum=False, create_constraint=True, name="participant_role"
)


def upgrade() -> None:
    op.execute("TRUNCATE TABLE messages, participants, chats")
    op.add_column("chats", sa.Column("type", _CHAT_TYPE, nullable=False))
    op.add_column("participants", sa.Column("role", _PARTICIPANT_ROLE, nullable=False))


def downgrade() -> None:
    op.drop_column("participants", "role")
    op.drop_column("chats", "type")
