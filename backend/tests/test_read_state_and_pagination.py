"""Ticket 09: where a Participant left off, and history that pages back stably.

The three things this file is about all rest on the same fact — that a Chat's
messages have a total order the database can be asked for. Ordering, the
cursor, and the unread count are that one fact read three ways.
"""

import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.models.chat import Chat, ChatType, Participant, ParticipantRole
from app.models.message import Message, MessageVisibility
from app.services.message import list_messages
from app.services.read_state import advanced_to
from tests.chats import open_chat, open_chat_of
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token, make_caller
from tests.messages import say


async def _chat_with(db: AsyncSession, *callers: Caller) -> Chat:
    chat = Chat(company_id=DEFAULT_COMPANY_ID, type=ChatType.STAFF, name=None)
    chat.participants = [
        Participant(company_id=DEFAULT_COMPANY_ID, user_id=c.id, role=ParticipantRole.STAFF)
        for c in callers
    ]
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


async def _write(
    db: AsyncSession,
    chat: Chat,
    sender: Caller,
    body: str,
    *,
    created_at: datetime,
    message_id: uuid.UUID | None = None,
    visibility: MessageVisibility = MessageVisibility.ALL,
) -> Message:
    """A Message written at a stated instant, which the send path cannot express.

    `created_at` is a server default on the way in, so a test about ordering
    has to put the row down itself: what it needs is two messages the clock
    cannot tell apart, and the clock will not produce them on request.
    """
    message = Message(
        id=message_id or uuid.uuid4(),
        company_id=DEFAULT_COMPANY_ID,
        chat_id=chat.id,
        sender_id=sender.id,
        sender_type="user",
        client_message_id=uuid.uuid4().hex,
        visibility=visibility,
        body=body,
        created_at=created_at,
    )
    db.add(message)
    await db.commit()
    return message


async def test_messages_sharing_an_instant_still_have_one_order(db_session: AsyncSession):
    """Two messages the clock cannot tell apart still come back in a fixed order.

    `created_at` alone leaves their relative order to whatever the plan
    happens to produce, and the cursor pages over exactly that order — so a
    tie is a place where a page can skip or repeat a message. The identifier
    is the tiebreaker: arbitrary, and the same every time it is asked.

    Written in the order that disagrees with the answer, so a read that is
    really returning insertion order fails here.
    """
    reader = make_caller()
    chat = await _chat_with(db_session, reader)
    instant = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    later = uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    earlier = uuid.UUID("00000000-0000-4000-8000-000000000000")

    await _write(db_session, chat, reader, "segunda", created_at=instant, message_id=later)
    await _write(db_session, chat, reader, "primeira", created_at=instant, message_id=earlier)

    page = await list_messages(db_session, CompanyScope.of(reader), reader, chat.id)

    assert [m.id for m in page.messages] == [earlier, later]


async def _page(
    client: AsyncClient,
    chat_id: str,
    headers: dict[str, str],
    *,
    before: str | None = None,
    limit: int | None = None,
) -> tuple[list[str], str | None]:
    """One page of history, as what it says and where it ends."""
    params: dict[str, str | int] = {}
    if before is not None:
        params["before"] = before
    if limit is not None:
        params["limit"] = limit
    response = await client.get(
        f"/chats/{chat_id}/messages", params=params, headers=headers
    )
    assert response.status_code == 200, response.text
    page = response.json()
    return [message["body"] for message in page["messages"]], page["next_cursor"]


async def test_history_pages_back_without_skipping_or_repeating_a_message(
    client: AsyncClient,
):
    """The whole point of a cursor, in the situation an offset gets wrong.

    Five messages, read two at a time from the newest end — with a sixth
    arriving after the first page, which is what a chat guarantees will happen
    while somebody scrolls. Under an offset the arrival shifts every row down
    one and page two hands back the oldest message of page one; under a cursor
    each page resumes from the row the last one ended on, and the arrival is
    simply somewhere the reader has not been.

    The union is asserted as well as each page, because the two failures are
    different: a skip loses a message from the union, a repeat is a message in
    it twice, and a test that only looked at bodies page by page could miss
    either.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, _ = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    for body in ("um", "dois", "tres", "quatro", "cinco"):
        assert (await say(client, chat_id, headers_a, body)).status_code == 201

    newest, first_cursor = await _page(client, chat_id, headers_a, limit=2)
    assert newest == ["quatro", "cinco"]
    assert first_cursor is not None

    assert (await say(client, chat_id, headers_a, "seis")).status_code == 201

    middle, second_cursor = await _page(
        client, chat_id, headers_a, before=first_cursor, limit=2
    )
    oldest, last_cursor = await _page(
        client, chat_id, headers_a, before=second_cursor, limit=2
    )

    assert middle == ["dois", "tres"]
    assert oldest == ["um"]
    assert last_cursor is None
    assert newest + middle + oldest == ["quatro", "cinco", "dois", "tres", "um"]


async def test_a_page_of_history_reads_oldest_first(client: AsyncClient):
    """A page is handed over in reading order, though it is taken from the end.

    The newest page is the one a thread opens on, and it is read downwards. The
    query walks backwards from the end to find it; reversing before answering
    is what keeps that an implementation detail rather than something every
    client has to undo.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, _ = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    for body in ("um", "dois", "tres"):
        await say(client, chat_id, headers_a, body)

    bodies, _ = await _page(client, chat_id, headers_a)

    assert bodies == ["um", "dois", "tres"]


async def test_a_cursor_the_service_did_not_issue_is_refused(client: AsyncClient):
    """Not answered with page one, which is what "ignore it" would amount to."""
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, _ = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]

    response = await client.get(
        f"/chats/{chat_id}/messages", params={"before": "nonsense"}, headers=headers_a
    )

    assert response.status_code == 422


async def _mark_read(
    client: AsyncClient,
    chat_id: str,
    headers: dict[str, str],
    *,
    read_at: datetime,
    message_id: str | None = None,
) -> Response:
    payload: dict[str, str] = {"read_at": read_at.isoformat()}
    if message_id is not None:
        payload["message_id"] = message_id
    return await client.post(f"/chats/{chat_id}/read", json=payload, headers=headers)


async def test_marking_as_read_records_where_the_participant_stopped(
    client: AsyncClient,
):
    """The watermark is a moment *and* a message, and both are written.

    The timestamp alone is what the unread count is computed from; the message
    is what a client re-anchors its scroll to. Storing only the first would
    leave "where I left off" to be guessed from a timestamp, which is exactly
    the guess that goes wrong when two messages share an instant.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    await say(client, chat_id, headers_a, "um")
    second = (await say(client, chat_id, headers_a, "dois")).json()

    marked = await _mark_read(
        client,
        chat_id,
        bearer(other_token),
        read_at=datetime.now(timezone.utc),
        message_id=second["id"],
    )

    assert marked.status_code == 200
    assert marked.json()["last_read_message_id"] == second["id"]
    assert marked.json()["last_read_at"] is not None


async def test_someone_who_is_not_in_the_chat_cannot_mark_it_read(client: AsyncClient):
    """The same answer every other read of a Chat they are not in gives.

    A refusal that distinguished "not yours" from "not there" would make this
    endpoint an oracle for which Chat identifiers exist — and marking as read
    is the cheapest probe on the service, since it needs nothing but the id.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, _ = caller_token()
    _, outsider_token = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]

    marked = await _mark_read(
        client, chat_id, bearer(outsider_token), read_at=datetime.now(timezone.utc)
    )

    assert marked.status_code == 404


def test_a_watermark_never_lands_in_the_future():
    """A clock running fast cannot mark as read what has not been said yet.

    Tested directly as well as through the API because the API can only ever
    show the clamp working — this shows what it is: a `min` against the
    service's own clock, which no skew survives.
    """
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    tomorrow = now + timedelta(days=1)

    assert advanced_to(None, tomorrow, now) == now


def test_a_watermark_takes_an_honest_timestamp_as_it_is():
    """The clamp is a ceiling, not a replacement — a slow clock is still read state."""
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    a_moment_ago = now - timedelta(seconds=30)

    assert advanced_to(None, a_moment_ago, now) == a_moment_ago


async def test_a_clock_running_fast_does_not_swallow_the_chats_unread_state(
    client: AsyncClient,
):
    """The same clamp, reached the way a real device reaches it.

    A phone a day ahead marks the Chat read, and everything said for the next
    twenty-four hours would be older than its watermark — the Chat would simply
    stop reporting anything unread, silently, until the clock caught up.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    await say(client, chat_id, headers_a, "um")

    marked = await _mark_read(
        client,
        chat_id,
        bearer(other_token),
        read_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    assert marked.status_code == 200
    stored = datetime.fromisoformat(marked.json()["last_read_at"])
    assert stored <= datetime.now(timezone.utc)


def test_a_watermark_does_not_move_backwards():
    """Reading old history is not unreading what came after it.

    Two clients on one account are the ordinary case: a phone at the bottom of
    the thread and a laptop scrolled up. Without this, whichever marks second
    wins, the count comes back, and the Chat re-notifies for messages the
    person has already read.
    """
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    already_read_to = now - timedelta(minutes=5)
    scrolled_back_to = now - timedelta(hours=2)

    assert advanced_to(already_read_to, scrolled_back_to, now) == already_read_to


def test_a_watermark_moves_when_there_is_something_new_to_move_it_to():
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    already_read_to = now - timedelta(hours=2)
    just_read_to = now - timedelta(minutes=5)

    assert advanced_to(already_read_to, just_read_to, now) == just_read_to


async def test_marking_an_older_position_leaves_the_message_it_stopped_at_alone(
    client: AsyncClient,
):
    """The two halves of the watermark move together or not at all.

    A refusal that held the timestamp but took the older message would leave a
    Participant whose read state says two different things — and the message
    is what a client re-anchors its scroll to, so it would send them back up
    the thread they had already finished.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    headers_b = bearer(other_token)
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    first = (await say(client, chat_id, headers_a, "um")).json()
    second = (await say(client, chat_id, headers_a, "dois")).json()

    now = datetime.now(timezone.utc)
    await _mark_read(client, chat_id, headers_b, read_at=now, message_id=second["id"])
    back_up = await _mark_read(
        client,
        chat_id,
        headers_b,
        read_at=now - timedelta(hours=1),
        message_id=first["id"],
    )

    assert back_up.json()["last_read_message_id"] == second["id"]


async def _listed(client: AsyncClient, chat_id: str, headers: dict[str, str]) -> dict:
    response = await client.get("/chats", headers=headers)
    assert response.status_code == 200
    return next(chat for chat in response.json() if chat["id"] == chat_id)


async def test_a_chat_reports_what_the_caller_has_not_read(client: AsyncClient):
    """The count is per caller, which is the whole of what makes it useful.

    Two people looking at the same Chat see different numbers, because the
    number is read off their own watermark and not off the Chat.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    for body in ("um", "dois", "tres"):
        await say(client, chat_id, headers_a, body)

    assert (await _listed(client, chat_id, bearer(other_token)))["unread_count"] == 3


async def test_what_the_caller_said_themselves_is_never_unread(client: AsyncClient):
    """Sending is having read it.

    Without this, a Chat nobody has replied to sits in the sender's own list
    with a badge for their own messages — and marking a Chat read would mean
    reading back what you just wrote.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, _ = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    for body in ("um", "dois", "tres"):
        await say(client, chat_id, headers_a, body)

    assert (await _listed(client, chat_id, headers_a))["unread_count"] == 0


async def test_marking_as_read_leaves_only_what_arrived_after_it(client: AsyncClient):
    """The count is what sits above the watermark, so moving it moves the count.

    Read to the second of three and one remains. Asserting the count *before*
    the mark as well is what distinguishes a watermark that works from a count
    that is quietly always zero.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    headers_b = bearer(other_token)
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    await say(client, chat_id, headers_a, "um")
    second = (await say(client, chat_id, headers_a, "dois")).json()
    await say(client, chat_id, headers_a, "tres")

    assert (await _listed(client, chat_id, headers_b))["unread_count"] == 3

    marked = await _mark_read(
        client,
        chat_id,
        headers_b,
        read_at=datetime.fromisoformat(second["created_at"]),
        message_id=second["id"],
    )

    assert marked.status_code == 200
    assert (await _listed(client, chat_id, headers_b))["unread_count"] == 1


async def test_a_chat_with_nothing_in_it_reports_nothing_unread(client: AsyncClient):
    """Zero is a real answer and has to be sent as one.

    A Chat missing from the aggregate is a Chat nobody has spoken in, not a
    Chat whose count is unknown — and a null there would leave every client
    deciding for itself what an absent count means.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]

    assert (await _listed(client, chat_id, bearer(other_token)))["unread_count"] == 0


async def _client_chat(client: AsyncClient) -> tuple[str, dict, dict]:
    """A Client Chat holding one of the Company's staff and one end client."""
    _, staff_token = caller_token()
    headers_staff = bearer(staff_token)
    end_client_id, end_client_token = caller_token(user_kind="client")

    created = await open_chat_of(
        client,
        headers_staff,
        (end_client_id, "client"),
        chat_type="client",
        name="Cliente e equipe",
    )
    return created.json()["id"], headers_staff, bearer(end_client_token)


async def test_a_staff_only_message_never_counts_for_an_end_client(client: AsyncClient):
    """Never learning one exists includes never watching a badge go up for one.

    A count is the thinnest possible leak and the hardest to notice: the end
    client is shown nothing, told nothing, and can still see that something
    happened. The staff side is asserted in the same test, because a count that
    stayed at zero for everybody would pass the half of this that matters least.
    """
    chat_id, headers_staff, headers_end_client = await _client_chat(client)

    assert (
        await say(client, chat_id, headers_staff, "segredo", visibility="staff_only")
    ).status_code == 201

    assert (await _listed(client, chat_id, headers_end_client))["unread_count"] == 0


async def test_a_staff_only_message_does_count_for_the_staff_who_did_not_send_it(
    client: AsyncClient,
):
    _, first_staff_token = caller_token()
    headers_first = bearer(first_staff_token)
    second_staff_id, second_staff_token = caller_token()
    end_client_id, _ = caller_token(user_kind="client")
    chat_id = (
        await open_chat_of(
            client,
            headers_first,
            (second_staff_id, "staff"),
            (end_client_id, "client"),
            chat_type="client",
            name="Cliente e equipe",
        )
    ).json()["id"]

    await say(client, chat_id, headers_first, "segredo", visibility="staff_only")

    listed = await _listed(client, chat_id, bearer(second_staff_token))
    assert listed["unread_count"] == 1


async def test_a_staff_only_message_is_not_a_gap_in_the_end_clients_pages(
    client: AsyncClient,
):
    """A page is a page of what the reader may read, not a page with a hole in it.

    Filtering after the limit is applied is the natural mistake, and it is the
    one the spec names: the end client would get a short page — two messages
    where they asked for three — and could count the difference. The filter is
    in the query, so the Staff-only Message is not in the sequence the cursor
    walks at all.
    """
    chat_id, headers_staff, headers_end_client = await _client_chat(client)
    for body, visibility in (
        ("um", "all"),
        ("segredo", "staff_only"),
        ("dois", "all"),
        ("tres", "all"),
    ):
        await say(client, chat_id, headers_staff, body, visibility=visibility)

    page, cursor = await _page(client, chat_id, headers_end_client, limit=3)

    assert page == ["um", "dois", "tres"]
    assert cursor is None


async def test_an_end_client_cannot_mark_read_by_naming_a_staff_only_message(
    client: AsyncClient,
):
    """The watermark names a Message, so naming one is a read, and it is filtered.

    Left unchecked this endpoint is an oracle: an end client walks identifiers
    and learns which ones the service accepts, which is learning which
    Staff-only Messages exist. It answers the way every other unreadable
    Message answers — not found.
    """
    chat_id, headers_staff, headers_end_client = await _client_chat(client)
    secret = (
        await say(client, chat_id, headers_staff, "segredo", visibility="staff_only")
    ).json()

    marked = await _mark_read(
        client,
        chat_id,
        headers_end_client,
        read_at=datetime.now(timezone.utc),
        message_id=secret["id"],
    )

    assert marked.status_code == 404


async def test_a_message_from_another_chat_cannot_be_the_watermark(client: AsyncClient):
    """Where somebody stopped reading has to be somewhere in the Chat they read."""
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    third_id, _ = caller_token()
    here = (await open_chat(client, headers_a, other_id)).json()["id"]
    # A third Participant, because a 1:1 between the same two people is the
    # same Chat reopened — there would be no "another Chat" to name.
    somewhere_else = (
        await open_chat(client, headers_a, other_id, third_id, name="Outro")
    ).json()["id"]
    strange = (await say(client, somewhere_else, headers_a, "noutro lugar")).json()

    marked = await _mark_read(
        client,
        here,
        bearer(other_token),
        read_at=datetime.now(timezone.utc),
        message_id=strange["id"],
    )

    assert marked.status_code == 404


async def test_a_read_timestamp_without_a_zone_is_refused(client: AsyncClient):
    """A timestamp with no zone names no instant, so it cannot clamp against one.

    The same argument the cursor makes. Left through, it reaches a comparison
    between an aware instant and a naive one and the request fails as a server
    error — which reads to the client as "the service is broken" rather than
    "that is not a timestamp", and is a 500 in the logs for a request that was
    always wrong.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]

    marked = await client.post(
        f"/chats/{chat_id}/read",
        json={"read_at": "2026-09-24T12:00:00"},
        headers=bearer(other_token),
    )

    assert marked.status_code == 422


async def test_a_chat_reports_where_this_caller_left_off(client: AsyncClient):
    """"Find where I left off" needs the position readable, not only writable.

    The unread count says how much is above the watermark; it does not say
    where the watermark is. A client coming back after a reconnect has to be
    able to ask — and the only other place the position appears is the response
    to the request that moved it, which that client did not make.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    headers_b = bearer(other_token)
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    await say(client, chat_id, headers_a, "um")
    second = (await say(client, chat_id, headers_a, "dois")).json()
    await _mark_read(
        client,
        chat_id,
        headers_b,
        read_at=datetime.fromisoformat(second["created_at"]),
        message_id=second["id"],
    )

    listed = await _listed(client, chat_id, headers_b)

    assert listed["last_read_message_id"] == second["id"]
    assert listed["last_read_at"] is not None


async def test_a_chat_reports_no_read_state_for_someone_who_has_read_nothing(
    client: AsyncClient,
):
    """Null is the honest answer, and distinguishable from having read the first message."""
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    await say(client, chat_id, headers_a, "um")

    listed = await _listed(client, chat_id, bearer(other_token))

    assert listed["last_read_at"] is None
    assert listed["last_read_message_id"] is None


async def test_marking_read_without_naming_a_message_keeps_the_last_one_named(
    client: AsyncClient,
):
    """A timestamp-only mark moves the watermark; it does not forget the anchor.

    Naming a Message is optional, so a client that only has a clock sends just
    the clock. Writing its absence through would erase the position a previous
    mark established — leaving read state that knows *when* somebody stopped
    and no longer knows *where*, which is the half a reconnecting client
    actually re-anchors on.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    other_id, other_token = caller_token()
    headers_b = bearer(other_token)
    chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
    first = (await say(client, chat_id, headers_a, "um")).json()
    await _mark_read(
        client,
        chat_id,
        headers_b,
        read_at=datetime.fromisoformat(first["created_at"]),
        message_id=first["id"],
    )

    await say(client, chat_id, headers_a, "dois")
    later = await _mark_read(client, chat_id, headers_b, read_at=datetime.now(timezone.utc))

    assert later.status_code == 200
    assert later.json()["last_read_message_id"] == first["id"]
    assert datetime.fromisoformat(later.json()["last_read_at"]) > datetime.fromisoformat(
        first["created_at"]
    )
