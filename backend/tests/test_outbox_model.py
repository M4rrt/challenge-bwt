"""What an outbox row carries, as the spec describes it.

The columns are asserted rather than assumed for the reason
`test_chat_model.py` gives: a column that arrives one ticket late is a
migration against live rows instead of a column definition.
"""

import sqlalchemy as sa

from app.models.outbox import OutboxEvent


def test_an_outbox_event_carries_its_company_address_payload_and_timestamps():
    columns = set(sa.inspect(OutboxEvent).columns.keys())

    assert columns == {
        "id",
        "company_id",
        "address",
        "payload",
        "created_at",
        "published_at",
    }


def test_an_unpublished_event_is_one_with_no_publication_moment():
    """Publishing is a moment, so being unpublished is the absence of one.

    The same shape as `Participant.left_at`. It is what makes "the oldest
    unpublished row" a `WHERE published_at IS NULL` rather than a flag somebody
    has to remember to keep in step with the timestamp beside it.
    """
    published_at = sa.inspect(OutboxEvent).columns["published_at"]

    assert published_at.nullable
