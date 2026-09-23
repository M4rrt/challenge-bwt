"""the outbox: delivery written in the transaction that made it true

Revision ID: e4a91b7c25d8
Revises: d2e5a81c6f47
Create Date: 2026-09-23

Realtime delivery used to happen inside the request. A row here replaces it:
written in the same transaction as the Message it announces, so a rollback
takes the announcement with it, and drained afterwards by a separate process,
so a crash between commit and publish leaves a record of what is still owed.

`address` carries the whole routing decision. Who may see a payload is settled
when the row is written, not when it is delivered — which is what stops a
future emitter from forgetting a filter.

One index earns its place beyond the Company's: a partial one over
`created_at` where `published_at IS NULL`. It is the only query the drain makes
and the only one the pending age is read from, and being partial is what keeps
it from growing with the published rows nothing ever scans that way.

No index on `address`. Reading back what went to one Chat during an incident
would want one, but nothing does that yet, and an index nobody queries is paid
for on every insert.
"""

import sqlalchemy as sa
from alembic import op

revision = "e4a91b7c25d8"
down_revision = "d2e5a81c6f47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_company_id", "outbox", ["company_id"])
    op.create_index(
        "ix_outbox_pending",
        "outbox",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_pending", table_name="outbox")
    op.drop_index("ix_outbox_company_id", table_name="outbox")
    op.drop_table("outbox")
