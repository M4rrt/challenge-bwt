import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.message_visibility import readable_visibilities
from app.models.chat import STILL_IN_THE_CHAT, Chat, ChatType, Participant, ParticipantRole
from app.models.message import Message, MessageVisibility
from app.schemas.chat import ChatCreate, ChatRead
from app.services.realtime import publish_to_user


_UNIX_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


class ChatShapeError(Exception):
    """The command describes a Chat the service will not build.

    Composition is validated against live data in the monolith, but the shape
    of the Chat is not something the monolith is the authority on — it is this
    service's own invariant, and the rules below are the whole of it.
    """

    detail = "invalid chat"


class GroupNameRequiredError(ChatShapeError):
    detail = "name is required for group chats"


class ClientInStaffChatError(ChatShapeError):
    detail = "a staff chat cannot contain an end client"


class UnknownUserKindError(ChatShapeError):
    detail = "unrecognised user kind"


async def _find_existing_one_to_one(
    db: AsyncSession, scope: CompanyScope, participant_ids: set[uuid.UUID], chat_type: ChatType
) -> Chat | None:
    """The Chat of this type whose current Participants are exactly these two, if there is one.

    Two Chats between the same pair are only the same Chat when they are the
    same kind of Chat — otherwise opening a Client Chat would hand back a Staff
    Chat, and the response would carry a `type` nobody asked for.
    """
    # The two aggregates look alike and count different things: the first asks
    # which Chats contain all of these people, the second asks which of those
    # contain nobody else — which is what keeps a group of three from answering
    # a request to open the 1:1 between two of them.
    chats_containing_all_of_them = (
        scope.select(Participant)
        .with_only_columns(Participant.chat_id)
        .where(Participant.user_id.in_(participant_ids), STILL_IN_THE_CHAT)
        .group_by(Participant.chat_id)
        .having(func.count(Participant.user_id) == len(participant_ids))
        .subquery()
    )
    chat_id = await db.scalar(
        scope.select(Participant)
        .with_only_columns(Participant.chat_id)
        .join(Chat, Chat.id == Participant.chat_id)
        .where(
            Participant.chat_id.in_(select(chats_containing_all_of_them)),
            Chat.type == chat_type,
            STILL_IN_THE_CHAT,
        )
        .group_by(Participant.chat_id)
        .having(func.count(Participant.user_id) == len(participant_ids))
    )
    if chat_id is None:
        return None
    return await db.scalar(
        scope.select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.participants))
    )


def _roles_by_user(caller: Caller, data: ChatCreate) -> dict[uuid.UUID, ParticipantRole]:
    """Every Participant's role, with the caller's taken from their own token.

    The command names the others because the service has no user table to look
    them up in, but it does not get to name the caller: that claim is one the
    monolith already signed.
    """
    try:
        caller_role = ParticipantRole(caller.user_kind)
    except ValueError:
        raise UnknownUserKindError() from None

    named = {participant.user_id: participant.user_kind for participant in data.participants}
    return named | {caller.id: caller_role}


async def create_chat(
    db: AsyncSession, scope: CompanyScope, caller: Caller, data: ChatCreate
) -> Chat:
    roles = _roles_by_user(caller, data)

    if data.type is ChatType.STAFF and ParticipantRole.CLIENT in roles.values():
        raise ClientInStaffChatError()

    if len(roles) > 2 and not data.name:
        raise GroupNameRequiredError()

    if len(roles) == 2:
        existing = await _find_existing_one_to_one(db, scope, set(roles), data.type)
        if existing is not None:
            return existing

    chat = Chat(company_id=scope.company_id, type=data.type, name=data.name)
    chat.participants = [
        Participant(company_id=scope.company_id, user_id=user_id, role=role)
        for user_id, role in roles.items()
    ]
    db.add(chat)
    await db.commit()
    await db.refresh(chat, attribute_names=["participants"])
    await notify_participants(db, scope, chat.id)
    return chat


async def list_chats(
    db: AsyncSession, scope: CompanyScope, caller: Caller
) -> list[ChatRead]:
    """The caller's Chats, most recently active first.

    The ordering is part of what a chat list *is* — a Chat with no messages
    sorts as if its last activity were the epoch, behind everything that has
    been spoken in — so it lives here rather than in the router, next to the
    query that knows which Chats there are.
    """
    result = await db.scalars(
        scope.select(Chat)
        .join(Participant)
        .where(Participant.user_id == caller.id, STILL_IN_THE_CHAT)
        .options(selectinload(Chat.participants))
    )
    chats = list(result.all())

    last_message_at = await get_last_message_at_by_chat(db, scope, visibilities_by_chat(caller, chats))
    listed = [ChatRead.of(chat, last_message_at.get(chat.id)) for chat in chats]
    listed.sort(key=lambda chat: chat.last_message_at or _UNIX_EPOCH, reverse=True)
    return listed


def visibilities_by_chat(
    caller: Caller, chats: Iterable[Chat]
) -> dict[uuid.UUID, Sequence[MessageVisibility]]:
    """What this caller may see in each of these Chats, asked of the one predicate."""
    return {
        chat.id: readable_visibilities(
            reader_kind=caller.user_kind,
            reader_company_id=caller.company_id,
            chat_company_id=chat.company_id,
            chat_type=chat.type,
        )
        for chat in chats
    }


async def get_last_message_at_by_chat(
    db: AsyncSession,
    scope: CompanyScope,
    visible: Mapping[uuid.UUID, Sequence[MessageVisibility]],
) -> dict[uuid.UUID, datetime]:
    """When each Chat last carried something the reader may actually read.

    Taking the visibilities rather than bare identifiers is what keeps a
    Staff-only Message out of the end client's chat list. `last_message_at` is
    the timestamp shown beside a Chat *and* the key it is ordered by, so an
    unfiltered maximum would tick the Chat forward and float it to the top
    every time staff said something the end client cannot read — announcing the
    Staff-only Message without quoting it.

    Chats are grouped by the set of visibilities rather than given a clause
    each: a single reader has at most one set per Chat type, so the OR stays
    two branches wide however long the list is.
    """
    if not visible:
        return {}

    chat_ids_by_visibilities: dict[tuple[MessageVisibility, ...], list[uuid.UUID]] = (
        defaultdict(list)
    )
    for chat_id, visibilities in visible.items():
        chat_ids_by_visibilities[tuple(visibilities)].append(chat_id)

    result = await db.execute(
        scope.select(Message)
        .with_only_columns(Message.chat_id, func.max(Message.created_at))
        .where(
            or_(
                *(
                    and_(
                        Message.chat_id.in_(chat_ids),
                        Message.visibility.in_(visibilities),
                    )
                    for visibilities, chat_ids in chat_ids_by_visibilities.items()
                )
            )
        )
        .group_by(Message.chat_id)
    )
    return dict(result.all())


async def notify_participants(
    db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID
) -> None:
    chat = await db.scalar(
        scope.select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.participants))
    )
    if chat is None:
        return

    # Every current Participant gets the same summary, Staff-only Message
    # included, because this is the live path and ticket 07 is what gives the
    # Company's staff an address of their own. Until it lands, an end client's
    # open chat list can twitch for a message their next `GET /chats` will not
    # show them — the transport gap ticket 07 exists to close.
    last_message_at = await get_last_message_at_by_chat(
        db, scope, {chat_id: list(MessageVisibility)}
    )
    payload = ChatRead.of(chat, last_message_at.get(chat_id)).model_dump_json()

    for participant in chat.current_participants:
        await publish_to_user(scope.company_id, participant.user_id, payload)
