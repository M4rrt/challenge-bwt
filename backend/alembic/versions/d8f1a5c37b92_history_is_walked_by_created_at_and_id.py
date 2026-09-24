"""history is walked by (created_at, id)

Revision ID: d8f1a5c37b92
Revises: c6b4e2a9d813
Create Date: 2026-09-24

The cursor pages a Chat's history by the pair the order is taken on, and
without an index matching that pair the database sorts the whole Chat to
return fifty rows — every page, and worst for exactly the long threads that
made paging necessary. The index is what makes the cursor faster than the
offset it replaced, rather than merely more correct than it.

`chat_id` leads because every read of history names one Chat, and it is
selective enough on its own that `company_id` would only widen the index: the
Company filter is still in the WHERE clause, and a Chat identifier belongs to
one Company by construction.

No column is added or changed here. The read state this ticket gives a reader
to — `last_read_at` and `last_read_message_id` — was added by `c9b2f4d7e130`,
which put them there ahead of time and said so.
"""

from alembic import op

revision = "d8f1a5c37b92"
down_revision = "c6b4e2a9d813"
branch_labels = None
depends_on = None

_INDEX = "ix_messages_chat_id_created_at_id"


def upgrade() -> None:
    op.create_index(_INDEX, "messages", ["chat_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="messages")
