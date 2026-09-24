"""The pagination cursor, tested away from any database.

The spec asks for this one directly as well as through the API, because what a
cursor has to be — opaque, exact, and hostile to a client that builds its own —
is a property of the encoding and not of any query that uses it.
"""

import base64
import uuid
from datetime import datetime, timezone

import pytest

from app.core.cursor import Cursor, InvalidCursorError, decode_cursor, encode_cursor


def test_a_cursor_round_trips_to_the_exact_instant_and_message():
    """Exact, down to the microsecond Postgres actually stores.

    A cursor that loses precision is a cursor that sits *between* two rows: the
    page after it either repeats the message it truncated or skips it, which is
    the one thing the cursor exists to prevent.
    """
    at = datetime(2026, 9, 24, 12, 0, 0, 123456, tzinfo=timezone.utc)
    message_id = uuid.uuid4()

    assert decode_cursor(encode_cursor(at, message_id)) == Cursor(at, message_id)


def test_a_cursor_does_not_read_as_a_timestamp_and_an_identifier():
    """Opaque on purpose, so nothing a client writes is a cursor.

    A cursor whose insides are legible is a cursor clients will assemble, and
    then the pair of columns it names can never change without breaking them.
    """
    at = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    message_id = uuid.uuid4()

    cursor = encode_cursor(at, message_id)

    assert str(message_id) not in cursor
    assert "2026-09-24" not in cursor


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not base64 at all!",
        base64.urlsafe_b64encode(b"no separator here").decode(),
        base64.urlsafe_b64encode(b"2026-09-24T12:00:00+00:00|not-a-uuid").decode(),
        base64.urlsafe_b64encode(b"whenever|" + str(uuid.uuid4()).encode()).decode(),
        base64.urlsafe_b64encode(b"2026-09-24T12:00:00|" + str(uuid.uuid4()).encode()).decode(),
    ],
)
def test_a_cursor_the_service_did_not_issue_is_refused(raw: str):
    """Refused rather than coerced into something that reads as page one.

    Every one of these is a cursor nothing here wrote. Falling back to "start
    from the top" would answer a corrupted scroll position with the newest
    page, silently — and a client re-anchored to the top of a long thread has
    no way to tell that from having genuinely reached it.
    """
    with pytest.raises(InvalidCursorError):
        decode_cursor(raw)


def test_a_naive_instant_cannot_become_a_cursor():
    """A timestamp with no zone names no instant, so it cannot name a position.

    Every timestamp in this service is stored with its zone. One arriving here
    without has come from somewhere that dropped it, and encoding it would put
    a silent local-time guess inside an opaque string nobody can inspect.
    """
    with pytest.raises(ValueError):
        encode_cursor(datetime(2026, 9, 24, 12, 0), uuid.uuid4())
