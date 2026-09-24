import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone

from sqlalchemy import ColumnElement, Select, and_, func, or_, select, true, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.orm.util import AliasedClass

from app.core.acting_user import ActingUser
from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.core.cursor import decode_cursor, encode_cursor, page_of
from app.core.message_visibility import readable_visibilities
from app.models.chat import STILL_IN_THE_CHAT, Chat, ChatType, Participant, ParticipantRole
from app.models.identity import UserProfile
from app.models.message import NEWEST_FIRST, Message, MessageVisibility
from app.schemas.chat import (
    AddParticipantCommand,
    ChatCommand,
    ChatPage,
    ChatRead,
    ParticipantIdentity,
)
from app.services.identity import message_responses, remember_identities
from app.services.outbox import enqueue
from app.services.realtime import address_for_user


_UNIX_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)
"""Where a Chat nobody has spoken in sorts: behind everything that has been.

The list is ordered by last activity and a silent Chat has none, so it needs a
stand-in instant rather than a null. Three things follow, and they are the
whole of why this constant exists — `_last_activity` and `_activity_of` below
point here rather than restating them:

- A null sorts wherever the plan puts it, and the cursor pages over exactly
  this order. A cursor over an order the plan chooses is a cursor that skips
  rows.
- Every silent Chat therefore shares one instant, which makes the order partial
  — so `Chat.id` is the tiebreaker, for the reason ticket 09 gave about two
  messages the clock cannot separate.
- It is read twice, once in SQL (a `COALESCE`) and once in Python, and the two
  have to agree to the microsecond: the cursor encodes microseconds, and a
  disagreement lands a page boundary between two readings of the same Chat.
"""

DEFAULT_CHAT_PAGE_LIMIT = 30
MAX_CHAT_PAGE_LIMIT = 100
"""How many Chats one request may ask for, with and without saying so.

Its own pair rather than the message page's, because the two lists are read at
different sizes: a thread opens on fifty messages, a sidebar on a screenful of
Chats. The ceiling is what keeps the cursor from being decorative — a client
that can ask for every Chat in one request never pages, and the ticket's
premise is a Company with hundreds of them.
"""


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


def _visible_in_the_joined_chat(caller: Caller) -> ColumnElement[bool]:
    """May this caller read this Message, decided from the Chat row in the query.

    `visible_to` in `services/message.py` asks the same thing of a Chat already
    loaded, and `in_a_chat_the_reader_may_see_it_in` below asks it of a set of
    identifiers. This third shape exists because the chat list has not chosen
    its Chats yet: it orders and pages by last activity, and last activity is
    what this filter decides — so the rule has to be inside the query rather
    than applied to its result.

    Three SQL shapes, one rule. All three derive their visibilities from
    `readable_visibilities`, which asks the single pure predicate in
    `core/message_visibility.py` — the shapes differ in what they have to hand,
    never in what they mean. That is the whole guard against ADR-0008's defect
    coming back, and it is why none of them spells a visibility out.

    It reads the type off `Chat.type`, so it only holds where a `Chat` is in the
    FROM clause. Two branches however many Chats there are, because the rule is
    a function of the type and there are two types.
    """
    return or_(
        *(
            and_(
                Chat.type == chat_type,
                Message.visibility.in_(
                    readable_visibilities(
                        reader_kind=caller.user_kind,
                        reader_company_id=caller.company_id,
                        chat_company_id=caller.company_id,
                        chat_type=chat_type,
                    )
                ),
            )
            for chat_type in ChatType
        )
    )


def _last_message_of_each_chat(
    scope: CompanyScope, caller: Caller
) -> AliasedClass[Message]:
    """One row per Chat: the newest Message in it this caller may read.

    A `LATERAL` rather than a prefetch, which is the ticket's own line and the
    spec's. Loading every Chat's messages to keep the last one reads a thread's
    whole history to show one line of it, and the cost is paid by exactly the
    Companies this list is for — the ones with years of messages behind each
    Chat. The lateral asks the index for one row per Chat and stops.

    `NEWEST_FIRST` is the message order itself, so the row previewed here is the
    row the thread opens on. Spelled any other way, the list could show a
    different "last message" than the Chat does.

    The visibility filter is inside the subquery, not outside it. Outside, a
    Staff-only Message would still *be* the newest row, and the end client's
    preview would come back empty rather than falling through to the last thing
    they may actually read — announcing the Staff-only Message by the hole it
    left.
    """
    return aliased(
        Message,
        scope.select(Message)
        .where(Message.chat_id == Chat.id, _visible_in_the_joined_chat(caller))
        .order_by(*NEWEST_FIRST)
        .limit(1)
        .lateral(),
        name="last_message",
    )


def _last_activity(last_message: AliasedClass[Message]) -> ColumnElement[datetime]:
    """When this Chat was last active, in SQL — see `_UNIX_EPOCH` for the silence.

    The ordering key and the cursor key are this one expression, so what the
    list sorts by and what a page resumes from cannot come apart.
    """
    return func.coalesce(last_message.created_at, _UNIX_EPOCH)


def _activity_of(last_message: Message | None) -> datetime:
    """The same value as `_last_activity`, read off the row the query returned.

    Computed here rather than selected as an extra column because the cursor is
    only ever built from the page's last row, and that row already carries it.
    Both spellings take the epoch from the one constant, which is what keeps
    them agreeing.
    """
    return last_message.created_at if last_message is not None else _UNIX_EPOCH


def _chats_of(
    scope: CompanyScope, caller: Caller, last_message: AliasedClass[Message]
) -> Select[tuple[Chat, Message | None]]:
    """The caller's own Chats, each with the last message they may read in it.

    The participation filter and the ordering are in one query on purpose. A
    cursor is a position in *this* caller's list; applied to a page some other
    query already chose, it would be a position in a list nobody asked for.
    """
    return (
        scope.select(Chat)
        .add_columns(last_message)
        .join(Participant, Participant.chat_id == Chat.id)
        .outerjoin(last_message, true())
        .where(Participant.user_id == caller.id, STILL_IN_THE_CHAT)
        .options(selectinload(Chat.participants))
    )


_LIKE_WILDCARDS = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})
"""The three characters `LIKE` reads as pattern rather than as text.

Somebody searching for a name types a name; nobody types a wildcard on
purpose. Left unescaped, a stray `_` matches any character and a `%` matches
the whole list — so a search that returned too much would look like the filter
being broken rather than like the input being read as a pattern.
"""


def _unaccented(text: ColumnElement[str] | str) -> ColumnElement[str]:
    """This text with its accents stripped, so a search can ignore them.

    Both sides go through it — the stored name and the pattern — because both
    spellings occur: somebody types "joao" looking for João, and somebody types
    "João" for a name the monolith stored without one. Normalising only the
    column would fix the first and leave the second.

    `immutable_unaccent` rather than `unaccent`, and the migration
    `f2b7d419ac53` explains which: the plain function is only STABLE, so it
    cannot appear in an index, and the index over exactly this expression is
    what keeps the filter from reading every profile in the Company. Spelled
    any other way here, the index silently stops being used.
    """
    return func.immutable_unaccent(text)


def _matching_the_search(
    scope: CompanyScope, caller: Caller, search: str
) -> ColumnElement[bool]:
    """Is this Chat one the caller would find by typing that.

    Two ways to match, because there are two ways a Chat is known by a name.
    Most are known by who is in them, which is the ticket's own sentence; a
    group is known by the name it carries, which is the only reason spec item
    21 makes a group carry one.

    The people are matched against the identity projection — a column in this
    database — and that is the whole of why the projection exists. Resolving
    names per row would mean filtering after the query, and a list filtered
    after the query cannot be paged: the page boundary would have to be decided
    before the filter that decides what is on either side of it. Resolving them
    from the monolith would be a request path that depends on it, which
    ADR-0010 forbids.

    The caller is excluded because they are a Participant of every Chat in
    their own list. Matching themselves would answer "find the person I was
    talking to" with the unfiltered list, which reads as the filter silently
    not working.

    The profile is joined on the Company as well as the user. The same user id
    exists in two Companies and each may describe that person differently, so
    joined on the user alone a staff member would find their Chats by typing a
    name nobody in their Company has ever seen — not a row crossing the
    boundary, but something harder to notice, because every Chat that comes
    back is genuinely theirs and only the reason is wrong. It is scoped by hand
    here because only the entity `scope.select` is given carries the filter
    automatically; `test_the_filter_does_not_match_a_name_from_another_company`
    asserts it from the edge for the same reason the unread count has its own
    boundary test.

    Both halves are normalised the same way. Two branches of one `OR` folding
    accents differently would find a group by its members' names but not by its
    own, which nobody would guess from the outside.
    """
    pattern = _unaccented(f"%{search.translate(_LIKE_WILDCARDS)}%")
    return or_(
        _unaccented(Chat.name).ilike(pattern, escape="\\"),
        scope.select(Participant)
        .join(
            UserProfile,
            and_(
                UserProfile.company_id == scope.company_id,
                UserProfile.user_id == Participant.user_id,
            ),
        )
        .where(
            Participant.chat_id == Chat.id,
            Participant.user_id != caller.id,
            STILL_IN_THE_CHAT,
            _unaccented(UserProfile.display_name).ilike(pattern, escape="\\"),
        )
        .exists(),
    )


async def list_chats(
    db: AsyncSession,
    scope: CompanyScope,
    caller: Caller,
    *,
    search: str | None = None,
    before: str | None = None,
    limit: int = DEFAULT_CHAT_PAGE_LIMIT,
) -> ChatPage:
    """A page of the caller's Chats, most recently active first.

    Ordered, filtered and paged in the database rather than in Python. That is
    not a performance preference: a list sorted after the fact cannot be paged
    at all, because the page boundary would have to be decided before the sort
    that decides what is on either side of it.

    `before` is a row, not a count, and the pair it names is the pair the order
    is taken on — so the page resumes at exactly the Chat the last one ended
    on, however much has been said above it while the person scrolled. Which
    is the one thing an offset cannot do, and the one thing a chat list
    guarantees will be tested.

    `search` narrows the same query rather than the page it produced, which is
    what makes the filtered list page exactly like the unfiltered one. A search
    of nothing but spaces is no search at all: it would otherwise be a pattern
    of `%  %`, which quietly answers a request for everything with a request
    for names containing two spaces.
    """
    last_message = _last_message_of_each_chat(scope, caller)
    activity = _last_activity(last_message)

    by_activity = (
        _chats_of(scope, caller, last_message)
        .order_by(activity.desc(), Chat.id.desc())
        .limit(limit + 1)
    )
    wanted = search.strip() if search else ""
    if wanted:
        by_activity = by_activity.where(_matching_the_search(scope, caller, wanted))
    if before is not None:
        cursor = decode_cursor(before)
        by_activity = by_activity.where(
            tuple_(activity, Chat.id) < tuple_(cursor.created_at, cursor.id)
        )

    page, there_is_more = page_of((await db.execute(by_activity)).all(), limit)

    visible = visibilities_by_chat(caller, [chat for chat, _ in page])
    unread = await unread_counts(db, scope, visible, for_user=caller.id)
    # Every preview's sender resolved in one query rather than one per Chat,
    # which is the whole reason the bulk helper exists: a page of thirty Chats
    # from thirty people is how a list quietly acquires a query per row.
    previews = {
        preview.chat_id: preview
        for preview in await message_responses(
            db, scope, [newest for _, newest in page if newest is not None]
        )
    }
    next_cursor = None
    if page and there_is_more:
        ended_on, its_newest = page[-1]
        next_cursor = encode_cursor(_activity_of(its_newest), ended_on.id)

    return ChatPage(
        chats=[
            ChatRead.of(
                chat,
                previews.get(chat.id),
                unread.get((chat.id, caller.id), 0),
                _read_by(chat, caller.id),
            )
            for chat, _ in page
        ],
        next_cursor=next_cursor,
    )


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

    The shape for a caller who already holds the Chats — which the unread count
    does, since the page has been chosen by the time it is asked. Its sibling
    `_visible_in_the_joined_chat` above is the same rule for a query that has
    not chosen them yet.

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


async def last_message_seen_by(
    db: AsyncSession,
    scope: CompanyScope,
    chat_id: uuid.UUID,
    visibilities: Sequence[MessageVisibility],
) -> Message | None:
    """The newest Message in this Chat that a reader with these visibilities may read.

    One Chat at a time, because its one caller — the chat-list push — announces
    one Chat and asks this once per role in it. The list endpoint asks the same
    question of every Chat at once and uses a `LATERAL` for it
    (`_last_message_of_each_chat`); the two are the same query in the two
    shapes the two call sites need, and both order by `NEWEST_FIRST` so the
    Chat a push describes and the Chat the list describes cannot disagree about
    what was last said in it.

    Taking the visibilities rather than trusting the caller to filter afterwards
    is what keeps a Staff-only Message out of the end client's list. It is both
    the preview *and*, through `last_message_at`, the key the list is ordered
    by — so an unfiltered newest row would tick the Chat forward and float it to
    the top every time staff said something the end client cannot read,
    announcing the Staff-only Message without quoting it.
    """
    return await db.scalar(
        scope.select(Message)
        .where(Message.chat_id == chat_id, Message.visibility.in_(visibilities))
        .order_by(*NEWEST_FIRST)
        .limit(1)
    )


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

    One payload per role rather than one per Chat. The preview is drawn from
    what that reader may actually read, so a Staff-only Message no longer stirs
    the end client's list: before this, every Participant got the same summary
    and the end client watched the Chat float to the top for a message they
    would never be shown.

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
        newest = await last_message_seen_by(db, scope, chat_id, visible[chat_id])
        # Resolved through the same bulk helper the list and the thread use, so
        # a name pushed here is the name the list would have shown — one
        # spelling of "who said this", and one place an anonymisation lands.
        preview = (await message_responses(db, scope, [newest]))[0] if newest else None
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
                    preview,
                    unread.get((chat_id, participant.user_id), 0),
                    participant,
                ).model_dump_json(),
            )
