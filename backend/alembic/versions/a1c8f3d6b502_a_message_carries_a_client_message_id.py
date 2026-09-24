"""a Message carries a client message id

Revision ID: a1c8f3d6b502
Revises: b5d2c9a4e716
Create Date: 2026-09-24

A sender's client generates this before it sends, and sends the same value
again when it retries. Together with the Chat and the sender it is what makes
a retry recognisable as a retry rather than as a second thing somebody said.

The column is nullable and the constraint is what enforces the rule, not the
column. A Message with no sender has no client to have generated one — the
webhook writes rows with `sender_id` and `client_message_id` both null — and
in PostgreSQL two nulls never collide, so those rows sit under the constraint
without ever meeting each other in it. Rows written before this migration are
in the same position: nobody supplied an id, and inventing one would be
inventing the retry history it exists to record. That a Participant's send
always carries one is enforced at the door, where the sender is there to be
refused, rather than by a NOT NULL that the webhook would have to lie to.

It is VARCHAR rather than UUID because the value is the client's, not the
service's: a client that identifies its retries with a ULID or a nanoid is
saying something the service understands perfectly well, and refusing it would
be refusing a shape for no reason the domain has. Bounded at 64 so the unique
index stays a small key.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1c8f3d6b502"
down_revision = "b5d2c9a4e716"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages", sa.Column("client_message_id", sa.String(length=64), nullable=True)
    )
    op.create_unique_constraint(
        "uq_messages_sender_client_message_id",
        "messages",
        ["chat_id", "sender_id", "client_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_messages_sender_client_message_id", "messages", type_="unique")
    op.drop_column("messages", "client_message_id")
