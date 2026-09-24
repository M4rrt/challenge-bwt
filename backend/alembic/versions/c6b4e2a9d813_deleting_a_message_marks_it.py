"""deleting a Message marks it

Revision ID: c6b4e2a9d813
Revises: a1c8f3d6b502
Create Date: 2026-09-24

Taking back what was said does not take away the row. Two things already
depend on it existing: the uniqueness constraint that makes a retry
recognisable — delete the row and the sender's next retry writes the message
again — and the cursor, which pages over what the rows hold, and would move
under a reader already scrolled past the gap. So the body is cleared and the
deletion is written down beside it.

All three columns are nullable together, and read together: `deleted_at` null
is what "not deleted" means, and the other two say nothing on their own. A
reason may be null even on a deleted row — deleting your own typo is not an
act that owes anybody an explanation, and a required reason would only have
produced a column full of "." — so it is the author, not the reason, that
every tombstone carries.

`deleted_by_user_id` is a bare UUID with no foreign key, like every other
identifier mirrored from the monolith: this service holds no user table.
"""

import sqlalchemy as sa
from alembic import op

revision = "c6b4e2a9d813"
down_revision = "a1c8f3d6b502"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("messages", sa.Column("deleted_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("messages", sa.Column("deletion_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "deletion_reason")
    op.drop_column("messages", "deleted_by_user_id")
    op.drop_column("messages", "deleted_at")
