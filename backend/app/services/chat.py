import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.acting_user import ActingUser
from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.message_visibility import readable_visibilities
from app.models.chat import STILL_IN_THE_CHAT, Chat, ChatType, Participant, ParticipantRole
from app.models.message import Message, MessageVisibility
from app.schemas.chat import AddParticipantCommand, ChatCommand, ChatRead, ParticipantIdentity
from app.services.identity import remember_identities
from app.services.outbox import enqueue
from app.services.realtime import address_for_user


_UNIX_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


class ChatShapeError(Exception):
    """The command describes a Chat the service will not build.

    Composition is validated against live data in the monolith, but the shape
    of the Chat is not something the monolith is the authority on — it is this
    service's own invariant, and the rules below are the whole of it.
    """

    detail = "invalid chat"


class ChatNotFoundError(Exception):
    """No Chat by that identifier in this Company.

    A Chat that never existed and a Chat belonging to somebody else are the
    same answer, which is the 404-not-403 decision: the refusal must not
    distinguish them.
    """


class GroupNameRequiredError(ChatShapeError):
    detail = "name is required for group chats"


class ClientInStaffChatError(ChatShapeError):
    detail = "a staff chat cannot contain an end client"


class EmptyChatError(ChatShapeError):
    detail = "a chat needs at least one participant"


class ForeignCompanyError(ChatShapeError):
    detail = "a participant from outside the company the command acts for"


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


def _role_inside_the_company(
    scope: CompanyScope, participant: ParticipantIdentity
) -> ParticipantRole:
    """This Participant's role, refusing them if they belong to another Company.

    The command carries each Participant's Company and the service files them
    under the one it is acting for. Those two have to be the same: a Chat whose
    members answered to a different boundary than the Chat itself would have
    `list_chats` joining across Companies, which is the one thing ADR-0007 says
    the code now has to carry on its own.
    """
    if participant.company_id != scope.company_id:
        raise ForeignCompanyError()
    return participant.user_kind


def _roles_inside_the_company(
    scope: CompanyScope, participants: Iterable[ParticipantIdentity]
) -> dict[uuid.UUID, ParticipantRole]:
    return {
        participant.user_id: _role_inside_the_company(scope, participant)
        for participant in participants
    }


def _validate_shape(
    chat_type: ChatType, name: str | None, roles: Mapping[uuid.UUID, ParticipantRole]
) -> None:
    """What the service is the authority on, asked in one place.

    Creating and adding both end up here, because the shape of a Chat is a
    property of the Chat and not of the moment it was reached: a Chat that a
    third Participant may be added to without a name is an unnamed group, and a
    rule only enforced on the way in is a rule with a way around it.

    Removing does not come through here, and that is deliberate. "A Chat is
    composed with somebody in it" is a rule about composing one; a Chat everyone
    has since left is not malformed, it is over — the rows stay, the messages
    stay attributable, and refusing the last departure would only trap the last
    person in a Chat they asked to leave.
    """
    if chat_type is ChatType.STAFF and ParticipantRole.CLIENT in roles.values():
        raise ClientInStaffChatError()

    if len(roles) > 2 and not name:
        raise GroupNameRequiredError()


async def create_chat(
    db: AsyncSession, scope: CompanyScope, acting: ActingUser, command: ChatCommand
) -> Chat:
    roles = _roles_inside_the_company(scope, command.participants)
    if not roles:
        raise EmptyChatError()
    _validate_shape(command.type, command.name, roles)

    # After validation, so a refused command leaves no trace of the people it
    # named, and before the reuse lookup, so that a command reopening a 1:1
    # still teaches the projection anybody it has not heard of yet.
    await remember_identities(db, scope, command.participants)

    if len(roles) == 2:
        existing = await _find_existing_one_to_one(db, scope, set(roles), command.type)
        if existing is not None:
            # This path used to return without committing, which was right when
            # it wrote nothing. It writes profiles now, and a session closed
            # with work open rolls back — so the identities the command carried
            # would be lost exactly on the redelivery that carried them again.
            await db.commit()
            return existing

    chat = Chat(
        company_id=scope.company_id,
        type=command.type,
        name=command.name,
        created_by_user_id=acting.id,
    )
    chat.participants = [
        Participant(company_id=scope.company_id, user_id=user_id, role=role)
        for user_id, role in roles.items()
    ]
    # The same shape as `_persist_and_announce`: flush for the identifiers,
    # enqueue, and commit once. Enqueueing after the commit would write rows
    # into a transaction nothing ever commits — `get_db` closes the session and
    # a session closed with work open rolls it back — so the Chat would exist
    # and nobody would be told it had been created.
    db.add(chat)
    await _announce_and_commit(db, scope, chat)
    return chat


async def _announce_and_commit(db: AsyncSession, scope: CompanyScope, chat: Chat) -> None:
    """Write the composition down and tell everyone still in the Chat.

    Flush for the identifiers, enqueue, and commit once — enqueueing after the
    commit would write the rows into a transaction nothing ever commits, since
    `get_db` closes the session and a session closed with work open rolls it
    back, so the Chat would change and nobody would be told.
    """
    await db.flush()
    await db.refresh(chat, attribute_names=["participants"])
    await enqueue_chat_summaries(db, scope, chat.id)
    await db.commit()


async def _chat_in_scope(db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID) -> Chat:
    chat = await db.scalar(
        scope.select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.participants))
    )
    if chat is None:
        raise ChatNotFoundError()
    return chat


async def add_participant(
    db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID, command: AddParticipantCommand
) -> Chat:
    """Put the named person in the Chat, and answer the same way twice.

    Composition arrives at-least-once, so naming somebody who is already in the
    Chat is the command having already succeeded, not an error — and it stays
    silent, because every Participant's chat list is pushed when composition
    changes and a redelivery would move every open list for no reason.

    Somebody who left and is named again comes back rather than gaining a second
    row: leaving is recorded on the row and not by deleting it, so reviving it is
    the only reading the unique constraint on (Chat, user) leaves for "add them
    back".
    """
    chat = await _chat_in_scope(db, scope, chat_id)
    role = _role_inside_the_company(scope, command.participant)
    user_id = command.participant.user_id

    # After the Company check, so a refused command leaves no trace of the
    # person it named, and before the early return below, so that a redelivery
    # still teaches the projection somebody it has not heard of — whoever joins
    # starts saying things, and a Participant the projection does not know is a
    # Participant whose messages are signed by nobody.
    await remember_identities(db, scope, [command.participant])

    participant = next((p for p in chat.participants if p.user_id == user_id), None)
    joining = participant is None or participant.left_at is not None

    # Whoever is already in the Chat keeps the role they joined with. The command
    # names a kind because the service has no user table to look one up in, not
    # because it re-decides what somebody in the Chat already is — a user whose
    # kind changes is an identity event, which is ticket 06.
    roles = {p.user_id: p.role for p in chat.current_participants}
    if joining:
        roles[user_id] = role

    # A name only answers the group rule, and only fills a gap. Moving one that
    # is already set would be a rename — a different command from a different
    # intention — and adopting one on a Chat that is still a 1:1 would let a
    # redelivery name a Chat nobody asked to name.
    name = chat.name or (command.name if len(roles) > 2 else None)
    _validate_shape(chat.type, name, roles)

    if not joining and name == chat.name:
        # Nothing about the Chat changed, but the identity the command carried
        # may still be new here, and this path writes it. A session closed with
        # work open rolls back, so returning without committing would discard
        # it exactly on the redelivery that carried it again.
        await db.commit()
        return chat

    if participant is None:
        chat.participants.append(
            Participant(company_id=scope.company_id, user_id=user_id, role=role)
        )
    elif joining:
        participant.left_at = None
        participant.role = role
    chat.name = name

    await _announce_and_commit(db, scope, chat)
    return chat


class ParticipantNotFoundError(Exception):
    """Nobody by that identifier has ever been in this Chat."""


async def remove_participant(
    db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID, user_id: uuid.UUID
) -> Chat:
    """Record that this person is no longer in the Chat.

    Leaving is a moment, not a deletion: the row stays so the messages they sent
    remain attributable and a Chat they were once in stays explicable. A command
    naming somebody who has already left is that command having already
    succeeded — the moment they left is not moved, because a redelivery is not a
    second departure.
    """
    chat = await _chat_in_scope(db, scope, chat_id)

    participant = next((p for p in chat.participants if p.user_id == user_id), None)
    if participant is None:
        raise ParticipantNotFoundError()

    if participant.left_at is None:
        participant.left_at = datetime.now(timezone.utc)
        await _announce_and_commit(db, scope, chat)
    return chat


def _read_by(chat: Chat, user_id: uuid.UUID) -> Participant | None:
    """This reader's own row in the Chat, which is where their read state lives.

    Already loaded — `list_chats` selectinloads the Participants to build the
    identifier list — so this is a lookup and not a query. None means a reader
    who is not a current Participant, which `list_chats` cannot produce and
    a future caller might.
    """
    return next(
        (p for p in chat.current_participants if p.user_id == user_id), None
    )


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

    visible = visibilities_by_chat(caller, chats)
    last_message_at = await get_last_message_at_by_chat(db, scope, visible)
    unread = await unread_counts(db, scope, visible, for_user=caller.id)
    listed = [
        ChatRead.of(
            chat,
            last_message_at.get(chat.id),
            unread.get((chat.id, caller.id), 0),
            _read_by(chat, caller.id),
        )
        for chat in chats
    ]
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


def in_a_chat_the_reader_may_see_it_in(
    visible: Mapping[uuid.UUID, Sequence[MessageVisibility]],
) -> ColumnElement[bool]:
    """Is this Message in one of those Chats, addressed where the reader can see it.

    Both aggregates a chat summary is built from need this clause and neither
    should spell it: they are the two places a Staff-only Message could leak
    into an end client's list — once as a timestamp that ticks forward, once as
    a badge that goes up — and a filter written twice is a filter that gets
    updated once.

    Chats are grouped by their set of visibilities rather than given a clause
    each: a single reader has at most one set per Chat type, so the OR stays two
    branches wide however long the list is.
    """
    chat_ids_by_visibilities: dict[tuple[MessageVisibility, ...], list[uuid.UUID]] = (
        defaultdict(list)
    )
    for chat_id, visibilities in visible.items():
        chat_ids_by_visibilities[tuple(visibilities)].append(chat_id)

    return or_(
        *(
            and_(
                Message.chat_id.in_(chat_ids),
                Message.visibility.in_(visibilities),
            )
            for visibilities, chat_ids in chat_ids_by_visibilities.items()
        )
    )


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

    The filter itself is `in_a_chat_the_reader_may_see_it_in`, shared with the
    unread count: those are the two ways a Staff-only Message could reach an end
    client's list, and they ask one clause rather than each writing their own.
    """
    if not visible:
        return {}

    result = await db.execute(
        scope.select(Message)
        .with_only_columns(Message.chat_id, func.max(Message.created_at))
        .where(in_a_chat_the_reader_may_see_it_in(visible))
        .group_by(Message.chat_id)
    )
    return dict(result.all())


async def unread_counts(
    db: AsyncSession,
    scope: CompanyScope,
    visible: Mapping[uuid.UUID, Sequence[MessageVisibility]],
    *,
    for_user: uuid.UUID | None = None,
) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    """How much each Participant of these Chats has not read, keyed by both.

    Three conditions make a Message unread, and all three are in the join rather
    than applied afterwards, so the count is the database's answer and not a
    list this service filtered:

    - it arrived after that Participant's watermark, which comes off their own
      row — the thresholds differ per Participant, so the watermark is joined
      rather than passed in;
    - somebody else said it, because sending is having read it — a Chat nobody
      has replied to would otherwise sit in the sender's own list with a badge
      for their own messages;
    - that Participant may read it. Taking the visibilities rather than bare
      identifiers is what keeps a Staff-only Message out of an end client's
      count: the end client is told nothing about one, and a badge that went up
      for a message they will never be shown tells them one is there.

    The join is an outer one and the answer covers every Participant asked
    about, including the ones with nothing unread. A missing key would mean
    "nobody has spoken here", which a caller would have to translate into zero —
    and the translation is the kind of thing one of two call sites forgets.
    """
    if not visible:
        return {}

    unread = and_(
        # Message is scoped by hand because the query is constructed over
        # Participant: both sides of a join have to answer to the boundary, and
        # only the entity `scope.select` was given carries it automatically.
        Message.company_id == scope.company_id,
        Message.chat_id == Participant.chat_id,
        Message.sender_id.is_distinct_from(Participant.user_id),
        or_(
            Participant.last_read_at.is_(None),
            Message.created_at > Participant.last_read_at,
        ),
        in_a_chat_the_reader_may_see_it_in(visible),
    )

    counted = (
        scope.select(Participant)
        .with_only_columns(
            Participant.chat_id, Participant.user_id, func.count(Message.id)
        )
        .outerjoin(Message, unread)
        .where(Participant.chat_id.in_(visible), STILL_IN_THE_CHAT)
        .group_by(Participant.chat_id, Participant.user_id)
    )
    if for_user is not None:
        counted = counted.where(Participant.user_id == for_user)

    result = await db.execute(counted)
    return {(chat_id, user_id): count for chat_id, user_id, count in result.all()}


async def enqueue_chat_summaries(
    db: AsyncSession, scope: CompanyScope, chat_id: uuid.UUID
) -> None:
    """Tell each Participant their chat list moved — with their own view of it.

    One payload per role rather than one per Chat. `last_message_at` is drawn
    from what that reader may actually read, so a Staff-only Message no longer
    stirs the end client's list: before this, every Participant got the same
    summary and the end client watched the Chat float to the top for a message
    they would never be shown.

    Grouped by role because the summary only differs by what the role may see,
    so a Chat with twenty staff in it costs one aggregate query, not twenty.
    """
    chat = await db.scalar(
        scope.select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.participants))
    )
    if chat is None:
        return

    participants_by_role: dict[ParticipantRole, list[Participant]] = defaultdict(list)
    for participant in chat.current_participants:
        participants_by_role[participant.role].append(participant)

    for role, participants in participants_by_role.items():
        visible = {
            chat_id: readable_visibilities(
                reader_kind=role,
                reader_company_id=chat.company_id,
                chat_company_id=chat.company_id,
                chat_type=chat.type,
            )
        }
        last_message_at = await get_last_message_at_by_chat(db, scope, visible)
        # The unread count is the one part of the summary that is not shared by
        # a role: it is read off each Participant's own watermark. One query per
        # role still answers for all of them, so the cost stays what the
        # grouping bought — an aggregate per role, not one per Participant.
        unread = await unread_counts(db, scope, visible)
        for participant in participants:
            enqueue(
                db,
                address_for_user(chat.company_id, participant.user_id),
                ChatRead.of(
                    chat,
                    last_message_at.get(chat_id),
                    unread.get((chat_id, participant.user_id), 0),
                    participant,
                ).model_dump_json(),
            )
