"""a Chat records who composed it

Revision ID: f3c9a1e70b24
Revises: e4a91b7c25d8
Create Date: 2026-09-23

Composition arrives as a command naming the user the monolith is acting for, and
that name now lands on the row. Without it the header was a condition for the
request and nothing else: any identifier passed, and afterwards nobody could
answer who opened a Chat.

The column is nullable, and the null means something true. A Chat composed
before this was opened by a browser with its own token, and the service never
recorded whose — writing a guess into a column that exists to answer "who did
this" would be worse than the gap it papers over. Every Chat composed since
carries one, because the command is refused without it.

Unlike `b7e1d0c4a92f` and `c1d4a7e90f32`, the old rows are kept rather than
truncated: no rule is evaluated against this column, so an unknown author
degrades nothing.
"""

import sqlalchemy as sa
from alembic import op

revision = "f3c9a1e70b24"
down_revision = "e4a91b7c25d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("chats", "created_by_user_id")
