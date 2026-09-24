"""the identity projection: names the service holds rather than fetches

Revision ID: b5d2c9a4e716
Revises: f3c9a1e70b24
Create Date: 2026-09-23

A display name is needed on every message response, and ADR-0010 forbids a
request path that calls the monolith — so the name has to be here already. This
table is where it is, fed by three inbound writes and never read across a
Company.

Unique on (company_id, user_id) rather than on user_id alone. The same user id
can exist in two Companies, which every fan-out address already carries for
that reason, and the constraint is also the conflict target the three writes
upsert against — so it is load-bearing twice over.

`user_kind` is a plain VARCHAR with no check constraint, unlike `chat_type`,
`participant_role` and `message_visibility`. Those three are the service's own
vocabulary and it refuses what it cannot express; this one mirrors the
monolith's, which is wider than two words, and a projection that refuses to
record what its source says is not a projection. No read path consults this
column today — the visibility rule takes the reader's kind from the token.

No index on `display_name`. Search by participant name is ticket 10 and will
want one — probably a trigram index rather than a b-tree, since the search is
by substring — and an index nobody queries is paid for on every write.
"""

import sqlalchemy as sa
from alembic import op

revision = "b5d2c9a4e716"
down_revision = "f3c9a1e70b24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("user_kind", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.UniqueConstraint("company_id", "user_id", name="uq_user_profiles_company_user"),
    )
    op.create_index("ix_user_profiles_company_id", "user_profiles", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_user_profiles_company_id", table_name="user_profiles")
    op.drop_table("user_profiles")
