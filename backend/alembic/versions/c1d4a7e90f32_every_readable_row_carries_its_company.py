"""every readable row carries its Company

Revision ID: c1d4a7e90f32
Revises: 2b3ac8cdc3c1
Create Date: 2026-09-22

ADR-0007 gave this service its own database and left Company isolation to code.
For code to filter by Company, the Company has to be on the row: Chats, their
Participants and their messages each carry the Company that owns them.

Rows written before this migration have no Company and cannot acquire a true
one — inventing a placeholder would silently file every old Chat under a
Company no token will ever name, which reads as data loss disguised as data.
They are deleted instead. This service has not been in production; the rows it
drops are development fixtures.
"""

import sqlalchemy as sa
from alembic import op

revision = "c1d4a7e90f32"
down_revision = "2b3ac8cdc3c1"
branch_labels = None
depends_on = None

_TABLES = ("messages", "conversation_participants", "conversations")


def upgrade() -> None:
    op.execute(f"TRUNCATE TABLE {', '.join(_TABLES)}")
    for table in _TABLES:
        op.add_column(table, sa.Column("company_id", sa.Uuid(), nullable=False))
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_company_id", table_name=table)
        op.drop_column(table, "company_id")
