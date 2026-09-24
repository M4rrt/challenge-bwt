"""Where each Participant left off: the watermark, and the rule for moving it.

What sits *above* the watermark is `unread_counts` in `services/chat.py`, next
to the other aggregate a chat summary is built from. It reads the column this
module writes, and lives there rather than here because a Chat summary is
assembled in one place — and because this module's refusal comes from there,
which is a dependency that only goes one way.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.models.chat import STILL_IN_THE_CHAT, Participant
from app.models.message import Message
from app.schemas.read_state import MarkRead, ReadState
from app.services.chat import ChatNotFoundError
from app.services.message import MessageNotFoundError, visible_to


def advanced_to(
    existing: datetime | None, asked: datetime, now: datetime
) -> datetime:
    """Where the watermark actually lands, given where the caller says it should.

    The caller's timestamp is their own clock's, because only they know when
    they looked. It is capped at the service's clock on the way in: a device
    running a day fast would otherwise mark as read everything said for the
    next day, and the Chat's unread state would not come back until the skew
    did — silently, with nothing to report.

    It only ever moves forward. Two clients on one account are the ordinary
    case — a phone at the bottom of the thread, a laptop scrolled up — and
    without this the one that marks second wins, the unread count comes back,
    and the Chat re-notifies for messages the person has already read. Marking
    as unread is a different act, deliberately asked for; this is not it
    happening by accident.

    A pure function over three instants, so the rule can be read without a
    session or a row, and tested without either.
    """
    clamped = min(asked, now)
    return clamped if existing is None else max(existing, clamped)


async def _participant_in(
    db: AsyncSession, scope: CompanyScope, caller: Caller, chat_id: uuid.UUID
) -> Participant:
    """The caller's own row in this Chat, with the Chat loaded beside it.

    `chat_of_participant` asks the same question from the other end and answers
    with the Chat, which is what sending and reading need. This path needs the
    row itself, because the watermark is on it — and it needs the Chat too, for
    the rule about which Messages the caller may name. One trip answers both.

    A Chat that is not there, is another Company's, or is one this caller is not
    in are one refusal, which is the 404-not-403 decision: marking as read needs
    nothing but an identifier, so a refusal that distinguished them would be the
    cheapest way there is to find out which Chats exist.
    """
    participant = await db.scalar(
        scope.select(Participant)
        .where(
            Participant.chat_id == chat_id,
            Participant.user_id == caller.id,
            STILL_IN_THE_CHAT,
        )
        .options(joinedload(Participant.chat))
    )
    if participant is None:
        raise ChatNotFoundError()
    return participant


async def _assert_readable_here(
    db: AsyncSession,
    scope: CompanyScope,
    caller: Caller,
    participant: Participant,
    message_id: uuid.UUID | None,
) -> None:
    """The named Message has to be one this caller could have read in this Chat.

    Naming a Message is a read of it, and it goes through the same filter every
    other read does. Left unchecked, this endpoint is an oracle: an end client
    walks identifiers, sees which ones are accepted, and learns which Staff-only
    Messages exist — without ever being shown one. It answers the way every
    unreadable Message answers, which is not found.

    Naming nothing is allowed and checks nothing: a caller who has read an empty
    Chat has no Message to point at, and the timestamp is a complete watermark
    on its own.
    """
    if message_id is None:
        return

    readable = await db.scalar(
        scope.select(Message).where(
            Message.id == message_id,
            Message.chat_id == participant.chat_id,
            visible_to(caller, participant.chat),
        )
    )
    if readable is None:
        raise MessageNotFoundError()


async def mark_read(
    db: AsyncSession,
    scope: CompanyScope,
    caller: Caller,
    chat_id: uuid.UUID,
    data: MarkRead,
) -> ReadState:
    """Move this Participant's watermark to where they say they have read.

    Three things stand between the request and the row, and each is a rule
    stated somewhere else: they have to be in the Chat, the Message they name
    has to be one they could have read in it, and the instant they claim has to
    survive `advanced_to`.

    The answer is the stored state rather than an echo of the request, because
    those last two can change it. A client that assumed its own timestamp had
    been written would show an unread count the service does not agree with.
    """
    participant = await _participant_in(db, scope, caller, chat_id)
    await _assert_readable_here(db, scope, caller, participant, data.message_id)

    advanced = advanced_to(
        participant.last_read_at, data.read_at, datetime.now(timezone.utc)
    )
    # The anchor follows the timestamp. A mark that does not move the watermark
    # — one going backwards, or one repeating where they already are — moves
    # neither half: keeping the timestamp while taking the older message would
    # leave read state saying two different things, and the message is what a
    # client re-anchors its scroll to, so it would send them back up a thread
    # they had finished.
    #
    # `or` rather than a plain assignment, because naming a Message is optional
    # and a client with only a clock sends only a clock. Writing that absence
    # through would erase the position an earlier mark established, leaving read
    # state that knows when somebody stopped and no longer knows where.
    if advanced != participant.last_read_at:
        participant.last_read_at = advanced
        participant.last_read_message_id = (
            data.message_id or participant.last_read_message_id
        )

    await db.commit()
    return ReadState.of(participant)
