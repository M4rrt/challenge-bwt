"""The Staff-only Message rule, exercised as the pure function it is.

ADR-0008 records this as the rule with the worst failure history in the source
module: a Participant loaded through a relation came back as the base user
class, an `isinstance` check answered "no" for an employee, and the rule failed
silently in both directions — sometimes dropping employees from their own
fan-out, sometimes keeping an end client in it.

The re-introducible form here is a token claiming a user kind the service does
not recognise. That branch is close to unreachable through the API, which is
why the rule is tested twice: here as a function, and in `test_messages.py`
through the endpoints that prove it is wired in.
"""

import uuid

from app.core.message_visibility import may_read
from app.models.chat import ChatType
from app.models.message import MessageVisibility

COMPANY = uuid.UUID("11111111-1111-1111-1111-111111111111")


def test_a_staff_reader_reads_an_ordinary_message():
    assert (
        may_read(
            reader_kind="staff",
            reader_company_id=COMPANY,
            chat_company_id=COMPANY,
            chat_type=ChatType.CLIENT,
            visibility=MessageVisibility.ALL,
        )
        is True
    )


def _may_read_staff_only(reader_kind: str, chat_type: ChatType = ChatType.CLIENT) -> bool:
    return may_read(
        reader_kind=reader_kind,
        reader_company_id=COMPANY,
        chat_company_id=COMPANY,
        chat_type=chat_type,
        visibility=MessageVisibility.STAFF_ONLY,
    )


def test_a_staff_reader_reads_a_staff_only_message_in_a_client_chat():
    assert _may_read_staff_only("staff") is True


def test_an_end_client_never_reads_a_staff_only_message():
    assert _may_read_staff_only("client") is False


def test_a_staff_only_message_in_a_staff_chat_is_read_by_nobody():
    """A state the write path refuses, so the read path answers on the narrow side.

    Nothing legal produces this row. A predicate that shrugged and said yes
    would mean the write rule is the only thing standing between a Staff-only
    Message and a reader — and this is the rule that has already failed once by
    being enforced in exactly one place.
    """
    assert _may_read_staff_only("staff", chat_type=ChatType.STAFF) is False


def test_an_unclassifiable_reader_reads_nothing():
    """The default-deny branch, and the concrete re-introduction of ADR-0008's defect.

    A token can claim any user kind; the service holds no user table to check
    it against. The claim `manager` is not staff and not client, and the old
    bug was exactly this question answered wrongly on the wide side. Denial
    covers ordinary messages too: a reader the rule cannot classify is a reader
    the rule has nothing true to say about, and an empty thread is a visible
    failure where a leaked Staff-only Message is a silent one.
    """
    verdicts = [
        may_read(
            reader_kind="manager",
            reader_company_id=COMPANY,
            chat_company_id=COMPANY,
            chat_type=chat_type,
            visibility=visibility,
        )
        for chat_type in ChatType
        for visibility in MessageVisibility
    ]

    assert verdicts == [False] * len(verdicts)


def test_a_reader_from_another_company_reads_nothing():
    """The predicate takes the Company as well, and is not the boundary.

    `CompanyScope` is what keeps another Company's rows out of the query in the
    first place, and this does not replace it. But the predicate is asked about
    a Chat and a reader, and a pair from two Companies has no true answer other
    than no — so it says so instead of ranging over the other three arguments
    as if the question were well formed.
    """
    verdicts = [
        may_read(
            reader_kind="staff",
            reader_company_id=COMPANY,
            chat_company_id=uuid.uuid4(),
            chat_type=chat_type,
            visibility=visibility,
        )
        for chat_type in ChatType
        for visibility in MessageVisibility
    ]

    assert verdicts == [False] * len(verdicts)
