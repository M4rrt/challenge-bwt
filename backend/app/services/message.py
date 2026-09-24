import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import ColumnElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.message_visibility import may_read, readable_visibilities
from app.models.chat import STILL_IN_THE_CHAT, Chat, Participant
from app.models.message import Message, MessageVisibility
from app.schemas.message import (
    MessageCreate,
    MessageDelete,
    MessageRead,
    WebhookMessageCreate,
)
from app.services.chat import ChatNotFoundError, enqueue_chat_summaries
from app.services.identity import profiles_by_user_id
from app.services.outbox import enqueue
from app.services.realtime import Address, address_for_chat, address_for_chat_staff


class VisibilityNotAllowedError(Exception):
    """The sender cannot address a Message this way in this Chat.

    Writing is the reading rule read backwards: a sender may address a Message
    only to a set they are themselves inside. That makes a Staff-only Message
    in a Staff Chat a refusal (nobody there to exclude, so the restriction is
    meaningless) and one written by an end client a refusal too (they would be
    writing something they could not then read), without a second rule anybody
    has to keep in step with `may_read`. It also means a sender whose user kind
    the rule cannot classify writes nothing at all, ordinary messages included
    — the default-deny branch reaching the write path by the same mechanism.

    Refusing beats storing it as an ordinary message: a silent downgrade tells
    the sender their message was restricted when it was not.
    """

    detail = "this sender cannot address a message this way in this chat"


class MessageNotFoundError(Exception):
    """No Message here this caller could name.

    Gone, never written, or addressed to a set they are not in — one answer for
    all three, for the reason `docs/decisions.md` gives about Chats. A reader
    who could tell "not yours to see" from "not there" could enumerate a Chat's
    Staff-only Messages by asking to delete each identifier in turn.
    """

    detail = "message not found"


class NotTheAuthorError(Exception):
    """Somebody else said this, so it is not this caller's to take back.

    Forbidden rather than hidden, which is the one place the 404-not-403 rule
    does not apply: this caller is in the Chat and has already read the Message.
    There is nothing left for a 404 to conceal, so it would only be a lie about
    why the request failed.
    """

    detail = "only the author may delete a message"


async def chat_of_participant(
    db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID, user_id: uuid.UUID
) -> Chat:
    """The Chat, if this user is currently in it — the two questions in one trip.

    Both reads now need the Chat itself and not merely permission to be there,
    because the visibility rule is asked about the Chat's type. Asking twice
    would put a second round trip on every send and every backlog fetch to
    learn something the first query's row already knew.

    A missing Chat, another Company's Chat and a Chat this user is not in are
    one answer, which is the 404-not-403 decision in `docs/decisions.md`: the
    refusal must not distinguish them. Send, backlog and the WebSocket handshake
    all ask through here, so there is one spelling of "is currently in this
    Chat" and the three cannot drift apart.
    """
    chat = await db.scalar(
        scope.select(Chat)
        .join(Participant, Participant.chat_id == Chat.id)
        .where(
            Chat.id == chat_id,
            Participant.user_id == user_id,
            STILL_IN_THE_CHAT,
        )
    )
    if chat is None:
        raise ChatNotFoundError()
    return chat


async def message_responses(
    db: AsyncSession, scope: CompanyScope, messages: Sequence[Message]
) -> list[MessageRead]:
    """These Messages as responses, with every sender's name resolved in one query.

    Resolution happens here rather than at each call site because a message
    table that stored the sender's name would make an anonymisation in the
    monolith unreachable — the name is a join, always, and this is where the
    join is. `MessageRead.of` takes the profile without a default so that a
    fifth call site cannot quietly send a null instead of going through here.
    """
    profiles = await profiles_by_user_id(
        db, scope, (message.sender_id for message in messages if message.sender_id)
    )
    return [
        MessageRead.of(
            message, profiles.get(message.sender_id) if message.sender_id else None
        )
        for message in messages
    ]


async def _message_already_sent(
    db: AsyncSession,
    scope: CompanyScope,
    chat_id: uuid.UUID,
    sender_id: uuid.UUID | None,
    client_message_id: str | None,
) -> Message | None:
    """The Message a refused insert was a retry of, if that is what it was.

    Asked only after the constraint has refused, never before. A lookup first
    would be a second opinion on a race the database is already deciding: two
    copies of the same retry arriving together would both find nothing, both
    insert, and one would still have to handle this. Going through the refusal
    means there is one path, and the ordinary sequential retry exercises it.

    None is a real answer, and the caller re-raises on it. A send with no client
    message id cannot have been a retry — nulls never collide — so an integrity
    error there is some other constraint failing, and swallowing it as "already
    sent" would turn a bug into a message that silently never arrived.
    """
    if client_message_id is None:
        return None
    return await db.scalar(
        scope.select(Message).where(
            Message.chat_id == chat_id,
            Message.sender_id == sender_id,
            Message.client_message_id == client_message_id,
        )
    )


def _visible_to(caller: Caller, chat: Chat) -> ColumnElement[bool]:
    """The WHERE clause for "a Message this caller may read in this Chat".

    Four arguments that always travel together, asked of the one predicate and
    turned into a filter in one place. Reading and deleting both go through it,
    so nothing is deletable that was not readable — and ADR-0008's defect, the
    rule evaluated in more than one place, has one fewer place to come back in.
    """
    return Message.visibility.in_(
        readable_visibilities(
            reader_kind=caller.user_kind,
            reader_company_id=caller.company_id,
            chat_company_id=chat.company_id,
            chat_type=chat.type,
        )
    )


def _address_of(message: Message) -> Address:
    """Where this Message is announced, decided from the visibility it carries.

    Both the send and the deletion ask here, so a tombstone is delivered to
    exactly the set that was shown the Message: a Staff-only Message is taken
    back on the staff address, and the end client who never saw it is never
    told that something they cannot name has gone.
    """
    if message.visibility is MessageVisibility.STAFF_ONLY:
        return address_for_chat_staff(message.company_id, message.chat_id)
    return address_for_chat(message.company_id, message.chat_id)


async def _announce(db: AsyncSession, scope: CompanyScope, message: Message) -> MessageRead:
    """This Message as a response, with the outbox row that carries it, unsent.

    The send and the deletion both end here, so what a socket receives and what
    the caller is handed are the same object built once — a tombstone cannot
    describe the Message differently from the way the send described it.

    It does not commit. The row belongs in whatever transaction the caller is
    already writing, which is the whole of `enqueue`'s contract.
    """
    response = (await message_responses(db, scope, [message]))[0]
    enqueue(db, _address_of(message), response.model_dump_json())
    return response


async def _persist_and_announce(
    db: AsyncSession, scope: CompanyScope, message: Message
) -> MessageRead:
    """The Message and everything that announces it, in one transaction.

    The flush is what makes that possible: it gives the row its identifier and
    its server-side timestamp without ending the transaction, so the payloads
    can be built from a Message that a rollback can still erase — taking every
    announcement of it along.

    The insert sits in a savepoint rather than the whole transaction, so the
    refusal that a retry arrives as undoes the refused INSERT and nothing else.
    A plain rollback works today only because both callers do nothing but read
    beforehand — and that is a condition on every future caller, held nowhere,
    that would fail by silently discarding their work.

    A retry leaves before any of that, and answers with the Message the sender
    already sent. Everything below it — the outbox row, the chat-list push — is
    an announcement of something new happening, and a retry is the sender's
    connection having been flaky, not a second thing happening. Re-announcing
    would move every open chat list for a message everybody already has.

    The answer is built from the stored row rather than from what the retry
    carried, so a client that resent a changed body does not get an edit
    endpoint nobody designed: the first send is the one that happened.
    """
    # Read off the instance before the flush: a refused insert leaves it
    # expired, and these three values are what the retry has to be looked up by.
    retry_key = (message.chat_id, message.sender_id, message.client_message_id)

    try:
        async with db.begin_nested():
            db.add(message)
            await db.flush()
    except IntegrityError:
        original = await _message_already_sent(db, scope, *retry_key)
        if original is None:
            raise
        return (await message_responses(db, scope, [original]))[0]

    await db.refresh(message)

    response = await _announce(db, scope, message)
    await enqueue_chat_summaries(db, scope, message.chat_id)

    await db.commit()
    return response


async def send_message(
    db: AsyncSession,
    scope: CompanyScope,
    caller: Caller,
    chat_id: uuid.UUID,
    data: MessageCreate,
) -> MessageRead:
    chat = await chat_of_participant(db, scope, chat_id, caller.id)

    if not may_read(
        reader_kind=caller.user_kind,
        reader_company_id=caller.company_id,
        chat_company_id=chat.company_id,
        chat_type=chat.type,
        visibility=data.visibility,
    ):
        raise VisibilityNotAllowedError()

    message = Message(
        company_id=caller.company_id,
        chat_id=chat_id,
        sender_id=caller.id,
        sender_type="user",
        client_message_id=data.client_message_id,
        visibility=data.visibility,
        body=data.body,
    )
    return await _persist_and_announce(db, scope, message)


async def assert_chat_exists(
    db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID
) -> Chat:
    chat = await db.scalar(
        scope.select(Chat).where(Chat.id == chat_id)
    )
    if chat is None:
        raise ChatNotFoundError()
    return chat


async def send_external_message(db: AsyncSession, data: WebhookMessageCreate) -> MessageRead:
    scope = CompanyScope(company_id=data.company_id)
    chat = await assert_chat_exists(db, scope, data.chat_id)

    message = Message(
        company_id=chat.company_id,
        chat_id=data.chat_id,
        sender_id=None,
        sender_type="external",
        source_label=data.source_label,
        visibility=MessageVisibility.ALL,
        body=data.body,
    )
    return await _persist_and_announce(db, scope, message)


async def delete_message(
    db: AsyncSession,
    scope: CompanyScope,
    caller: Caller,
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    data: MessageDelete,
) -> MessageRead:
    """Take back what was said, without taking the Message out of the thread.

    The row stays and the body is cleared, which is the whole of the decision in
    `docs/decisions.md`: the uniqueness constraint would otherwise let the
    sender's next retry write the message again, and the cursor pages over rows
    that have to still be there. What everyone else sees change is a message
    turning into a marker, in the place it already occupied.

    Reached through the same two filters as reading it — a current Participant
    of the Chat, and a visibility their kind may see — so nothing is deletable
    that was not readable, and a Message addressed past this caller answers the
    same way as one that was never written.

    The tombstone goes out on the address the Message was announced on, so the
    people who were shown it are exactly the people told it is gone.

    Deleting what is already deleted answers with the existing marker and
    writes nothing. Overwriting would let a double-click put a null where the
    first request's reason was, and move `deleted_at` to the moment of the
    accident — unrecording the why, which is half of what the row is for.
    """
    chat = await chat_of_participant(db, scope, chat_id, caller.id)

    message = await db.scalar(
        scope.select(Message).where(
            Message.id == message_id,
            Message.chat_id == chat_id,
            _visible_to(caller, chat),
        )
    )
    if message is None:
        raise MessageNotFoundError()
    if message.sender_id != caller.id:
        raise NotTheAuthorError()
    if message.deleted_at is not None:
        return (await message_responses(db, scope, [message]))[0]

    message.body = ""
    message.deleted_at = datetime.now(timezone.utc)
    message.deleted_by_user_id = caller.id
    message.deletion_reason = data.reason

    response = await _announce(db, scope, message)
    await db.commit()
    return response


async def list_messages(
    db: AsyncSession, scope: CompanyScope, caller: Caller, chat_id: uuid.UUID
) -> list[MessageRead]:
    chat = await chat_of_participant(db, scope, chat_id, caller.id)

    result = await db.scalars(
        scope.select(Message)
        .where(
            Message.chat_id == chat_id,
            _visible_to(caller, chat),
        )
        .order_by(Message.created_at)
    )
    return await message_responses(db, scope, list(result.all()))
