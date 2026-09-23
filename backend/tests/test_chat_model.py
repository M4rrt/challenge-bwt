"""What Chat and Participant carry, as `CONTEXT.md` and the spec describe them.

Read state has no reader yet — ticket 09 adds it. It is asserted here anyway,
because the checklist this file is built from names it as something the entity
*carries*, and a column that arrives one ticket late is a migration against live
rows rather than a column definition.

`created_by_user_id` has no reader either, and never will have one on a request
path: it is there so that "there is no Chat without an author" is answerable
after the fact and not only enforced at the door.
"""

import sqlalchemy as sa

from app.models.chat import Chat, Participant


def test_participants_relationship_orders_by_user_id():
    relationship = sa.inspect(Chat).relationships["participants"]

    assert relationship.order_by == (Participant.user_id,)


def test_a_chat_carries_its_company_type_name_author_and_timestamps():
    columns = set(sa.inspect(Chat).columns.keys())

    assert columns == {
        "id",
        "company_id",
        "type",
        "name",
        "created_by_user_id",
        "created_at",
        "updated_at",
    }


def test_a_participant_carries_its_chat_user_company_role_and_read_state():
    columns = set(sa.inspect(Participant).columns.keys())

    assert columns == {
        "id",
        "chat_id",
        "user_id",
        "company_id",
        "role",
        "joined_at",
        "left_at",
        "last_read_at",
        "last_read_message_id",
    }


def test_a_chat_that_has_not_been_left_is_open_ended():
    """Leaving is a moment, so not having left is the absence of one."""
    left_at = sa.inspect(Participant).columns["left_at"]

    assert left_at.nullable


def test_the_type_and_role_columns_hold_the_words_the_rest_of_the_service_uses():
    """SQLAlchemy stores a Python enum by member *name* unless told otherwise.

    `ChatType.STAFF` lands in the column as `STAFF` while every payload,
    migration, log line and glossary entry says `staff`, and nothing reading
    through the mapper can tell: it maps the name back to the member on the way
    out. What surfaced it was the CHECK constraint, written from the
    migration's own spelling of the values.
    """
    chat_type = sa.inspect(Chat).columns["type"].type
    participant_role = sa.inspect(Participant).columns["role"].type

    assert set(chat_type.enums) == {"staff", "client"}
    assert set(participant_role.enums) == {"staff", "client"}
