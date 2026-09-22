"""mirrored user identifiers carry no foreign key

Revision ID: 4b52e66b2b99
Revises: 86b698e95475
Create Date: 2026-09-22

The users a Chat refers to live in the monolith. Their identifiers arrive here
as opaque values, so the columns holding them stop pointing at a local table.
"""

from alembic import op

revision = "4b52e66b2b99"
down_revision = "86b698e95475"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("conversation_participants_user_id_fkey", "conversation_participants")
    op.drop_constraint("messages_sender_id_fkey", "messages")


def downgrade() -> None:
    op.create_foreign_key(
        "conversation_participants_user_id_fkey",
        "conversation_participants",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key("messages_sender_id_fkey", "messages", "users", ["sender_id"], ["id"])
