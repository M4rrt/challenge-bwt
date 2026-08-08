"""use clock_timestamp for message created_at default

Revision ID: ed8d3b5f889d
Revises: 76e24d85b3c1
Create Date: 2026-08-07 21:19:51.467367

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed8d3b5f889d'
down_revision: Union[str, Sequence[str], None] = '76e24d85b3c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'messages',
        'created_at',
        server_default=sa.text('clock_timestamp()'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'messages',
        'created_at',
        server_default=sa.text('now()'),
    )
