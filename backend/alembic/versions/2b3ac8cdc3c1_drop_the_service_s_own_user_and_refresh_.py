"""drop the service's own user and refresh token tables

Revision ID: 2b3ac8cdc3c1
Revises: 4b52e66b2b99
Create Date: 2026-09-22

The monolith is the only place a password exists. The service keeps no account
of its own and nothing to refresh, so both tables go.
"""

import sqlalchemy as sa
from alembic import op

revision = "2b3ac8cdc3c1"
down_revision = "4b52e66b2b99"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("users")


def downgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
