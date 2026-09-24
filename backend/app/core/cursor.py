"""A position in a Chat's history, as something a client can hold but not write.

Paging a chat by offset is paging by a number that means something different
every time it is used: a message arriving while somebody scrolls shifts every
row down one, and the next page repeats what they just read. Arrivals are the
one thing a chat guarantees, so the position has to name a row rather than
count from an end — which is a cursor over the two columns the order is taken
on, `(created_at, id)`.

It is opaque because the pair it names is an implementation detail. Handed out
as a legible timestamp and identifier, clients assemble their own, and then the
ordering can never be changed without breaking them. Base64 is not a secret
here and is not meant to be one — it is a shape that says "this came from us,
give it back unaltered".
"""

import base64
import binascii
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, TypeVar

T = TypeVar("T")


class InvalidCursorError(ValueError):
    """This is not a cursor this service issued.

    Refused rather than treated as "no cursor". Falling back to the newest page
    would answer a corrupted scroll position with the top of the thread and say
    nothing, and a client cannot tell that from having genuinely reached it.
    """

    detail = "invalid cursor"


@dataclass(frozen=True)
class Cursor:
    """The last row a page ended on: the instant, and which message at it."""

    created_at: datetime
    id: uuid.UUID


_SEPARATOR = "|"


def encode_cursor(created_at: datetime, message_id: uuid.UUID) -> str:
    """Where a page ended, as one opaque string.

    The instant is written in ISO 8601, which carries microseconds exactly —
    the precision Postgres stores a `timestamptz` at. Anything lossier would
    land the cursor *between* two rows, and the next page would then either
    repeat the message it truncated or skip it.
    """
    if created_at.tzinfo is None:
        raise ValueError("a cursor names an instant, and a naive datetime names none")
    raw = f"{created_at.isoformat()}{_SEPARATOR}{message_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(raw: str) -> Cursor:
    """The position a client handed back, or a refusal.

    Every way this can fail is one failure — a string nothing here wrote — so
    they arrive as one error. Padding is restored rather than required, because
    it is stripped on the way out: `urlsafe_b64encode` pads to a multiple of
    four with `=`, which is noise in a query string and survives a round trip
    through fewer clients than it should.
    """
    try:
        padded = raw + "=" * (-len(raw) % 4)
        at, separator, message_id = (
            base64.urlsafe_b64decode(padded).decode().partition(_SEPARATOR)
        )
        if not separator:
            return _refuse()
        created_at = datetime.fromisoformat(at)
        cursor = Cursor(created_at, uuid.UUID(message_id))
    except (binascii.Error, UnicodeDecodeError, ValueError) as broken:
        return _refuse(broken)

    if cursor.created_at.tzinfo is None:
        return _refuse()
    return cursor


def _refuse(cause: Exception | None = None) -> NoReturn:
    """Every way a cursor can be wrong, arriving as one refusal.

    `NoReturn` rather than `Cursor`: the call sites above are spelled `return
    _refuse(...)` because that is how they read, but the signature says what
    actually happens rather than what the call site looks like.
    """
    raise InvalidCursorError(InvalidCursorError.detail) from cause


def page_of(found: Sequence[T], limit: int) -> tuple[list[T], bool]:
    """The rows the caller asked for, and whether there are more behind them.

    Every cursor read here fetches one row more than it was asked for and drops
    it. That extra row is the whole of how a response knows whether to send a
    cursor: without it, reaching the end and landing exactly on it are
    indistinguishable, and the client is left holding a cursor that fetches
    nothing — with no way to know it has finished until it has asked.

    It is four lines, and it is here rather than written out at each read
    because the two reads that page — a Chat's history and the chat list — had
    it twice, along with the argument above. A page shape written twice is a
    page shape updated once, which is the same reason the visibility rule has
    one home.

    What it deliberately does not do is build the cursor. Where a page resumes
    from is the one part that differs: history walks backwards and reverses,
    the chat list does not, and the pair each encodes comes off different
    columns. Folding that in would take a callback to hide a single line.
    """
    return list(found[:limit]), len(found) > limit
