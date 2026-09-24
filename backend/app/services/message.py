import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.message_visibility import may_read, readable_visibilities
from app.models.chat import STILL_IN_THE_CHAT, Chat, Participant
from app.models.message import Message, MessageVisibility
from app.schemas.message import MessageCreate, MessageRead, WebhookMessageCreate
from app.services.chat import ChatNotFoundError, enqueue_chat_summaries
from app.services.identity import profiles_by_user_id
from app.services.outbox import enqueue
from app.services.realtime import address_for_chat, address_for_chat_staff


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


async def _persist_and_announce(
    db: AsyncSession, scope: CompanyScope, message: Message
) -> MessageRead:
    """The Message and everything that announces it, in one transaction.

    The flush is what makes that possible: it gives the row its identifier and
    its server-side timestamp without ending the transaction, so the payloads
    can be built from a Message that a rollback can still erase — taking every
    announcement of it along.

    The address is chosen here, once, from the visibility the sender already
    had to be entitled to. A Staff-only Message goes to the staff address and
    is therefore never delivered to an end client's socket, because that socket
    is not listening there — not because anything downstream checked.
    """
    db.add(message)
    await db.flush()
    await db.refresh(message)

    response = (await message_responses(db, scope, [message]))[0]
    address = (
        address_for_chat_staff(message.company_id, message.chat_id)
        if message.visibility is MessageVisibility.STAFF_ONLY
        else address_for_chat(message.company_id, message.chat_id)
    )
    enqueue(db, address, response.model_dump_json())
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


async def list_messages(
    db: AsyncSession, scope: CompanyScope, caller: Caller, chat_id: uuid.UUID
) -> list[MessageRead]:
    chat = await chat_of_participant(db, scope, chat_id, caller.id)

    result = await db.scalars(
        scope.select(Message)
        .where(
            Message.chat_id == chat_id,
            Message.visibility.in_(
                readable_visibilities(
                    reader_kind=caller.user_kind,
                    reader_company_id=caller.company_id,
                    chat_company_id=chat.company_id,
                    chat_type=chat.type,
                )
            ),
        )
        .order_by(Message.created_at)
    )
    return await message_responses(db, scope, list(result.all()))
