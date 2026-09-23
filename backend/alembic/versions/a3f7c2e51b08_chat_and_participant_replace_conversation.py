"""Chat and Participant replace Conversation

Revision ID: a3f7c2e51b08
Revises: c1d4a7e90f32
Create Date: 2026-09-23

`CONTEXT.md` names the container Chat and the link between a user and one
Participant, and lists Conversation under _Avoid_. The word survived the move
off Django because nothing failed when it did; this migration takes it out of
the schema, where it was doing the most damage — a column named
`conversation_id` teaches every future reader the wrong word before they reach
the glossary.

Nothing is dropped and no row moves: tables, columns, indexes and constraints
are renamed in place. The earlier migrations keep saying `conversations`
because they describe a schema that really did carry that name.
"""

from alembic import op

revision = "a3f7c2e51b08"
down_revision = "c1d4a7e90f32"
branch_labels = None
depends_on = None


def _rename_constraint(table: str, old: str, new: str) -> None:
    op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')


def _rename_index(old: str, new: str) -> None:
    op.execute(f'ALTER INDEX "{old}" RENAME TO "{new}"')


def upgrade() -> None:
    op.rename_table("conversations", "chats")
    op.rename_table("conversation_participants", "participants")
    op.alter_column("participants", "conversation_id", new_column_name="chat_id")
    op.alter_column("messages", "conversation_id", new_column_name="chat_id")

    _rename_constraint("chats", "conversations_pkey", "chats_pkey")
    _rename_constraint("participants", "conversation_participants_pkey", "participants_pkey")
    _rename_constraint(
        "participants",
        "conversation_participants_conversation_id_user_id_key",
        "participants_chat_id_user_id_key",
    )
    _rename_constraint(
        "participants",
        "conversation_participants_conversation_id_fkey",
        "participants_chat_id_fkey",
    )
    _rename_constraint("messages", "messages_conversation_id_fkey", "messages_chat_id_fkey")

    _rename_index("ix_conversations_company_id", "ix_chats_company_id")
    _rename_index("ix_conversation_participants_company_id", "ix_participants_company_id")


def downgrade() -> None:
    op.rename_table("chats", "conversations")
    op.rename_table("participants", "conversation_participants")
    op.alter_column("conversation_participants", "chat_id", new_column_name="conversation_id")
    op.alter_column("messages", "chat_id", new_column_name="conversation_id")

    _rename_constraint("conversations", "chats_pkey", "conversations_pkey")
    _rename_constraint(
        "conversation_participants", "participants_pkey", "conversation_participants_pkey"
    )
    _rename_constraint(
        "conversation_participants",
        "participants_chat_id_user_id_key",
        "conversation_participants_conversation_id_user_id_key",
    )
    _rename_constraint(
        "conversation_participants",
        "participants_chat_id_fkey",
        "conversation_participants_conversation_id_fkey",
    )
    _rename_constraint("messages", "messages_chat_id_fkey", "messages_conversation_id_fkey")

    _rename_index("ix_chats_company_id", "ix_conversations_company_id")
    _rename_index("ix_participants_company_id", "ix_conversation_participants_company_id")
