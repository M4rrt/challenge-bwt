"""Who may read a Message: the one place the Staff-only rule is decided.

This is `company_scope.py`'s sibling. Both are rules that lost their Django
floor in the move to FastAPI, and both fail silently when they fail: isolation
leaks a row, visibility leaks a whisper. ADR-0008 records that this one has
already failed once — a Participant loaded through a relation came back as the
base user class, an `isinstance` check answered "no" for an employee, and the
rule dropped employees from their own fan-out while keeping end clients in it.

What that bug really was: the rule was evaluated in more than one place, over a
value nobody had pinned down. So the rule here is a pure function over four
arguments and nothing else — no session, no relation to load, no row whose
class might surprise it — and every read path asks it rather than restating it.
Queries included: `readable_visibilities` derives the WHERE clause by asking
`may_read` about each visibility, so there is no second spelling of the rule
that a query could drift away from.

The default-deny branch is the bug's re-introducible form. A token can claim
any user kind and the service holds no user table to check it against, so a
kind the rule cannot classify is answered no — for ordinary messages too. An
empty thread is a failure somebody reports; a leaked Staff-only Message is one
nobody sees.
"""

import uuid

from app.models.chat import ChatType, ParticipantRole
from app.models.message import MessageVisibility


def may_read(
    *,
    reader_kind: str,
    reader_company_id: uuid.UUID,
    chat_company_id: uuid.UUID,
    chat_type: ChatType,
    visibility: MessageVisibility,
) -> bool:
    """Whether a reader of this kind, in this Company, may read this Message.

    It says nothing about participation: whether the reader belongs in the Chat
    at all is a separate question, asked by `chat_of_participant` before this
    one is reached. This answers only what their kind entitles them to see once
    they are in.
    """
    if reader_company_id != chat_company_id:
        return False

    try:
        role = ParticipantRole(reader_kind)
    except ValueError:
        return False

    if visibility is MessageVisibility.ALL:
        return True
    return chat_type is ChatType.CLIENT and role is ParticipantRole.STAFF


def readable_visibilities(
    *,
    reader_kind: str,
    reader_company_id: uuid.UUID,
    chat_company_id: uuid.UUID,
    chat_type: ChatType,
) -> list[MessageVisibility]:
    """The visibilities this reader may see, ready to go into a WHERE clause.

    Asked of `may_read` rather than restated as SQL. A hand-written filter would
    be a second spelling of a rule that has already failed once by being
    evaluated in more than one place, and the two would drift the first time
    only one of them was updated.

    An empty list is a real answer: a reader the rule cannot classify may see no
    visibility at all, and an `IN ()` returns nothing, which is what that means.
    """
    return [
        visibility
        for visibility in MessageVisibility
        if may_read(
            reader_kind=reader_kind,
            reader_company_id=reader_company_id,
            chat_company_id=chat_company_id,
            chat_type=chat_type,
            visibility=visibility,
        )
    ]
