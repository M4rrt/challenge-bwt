"""The chat list: ordered by last activity, paged by cursor, filtered by name.

Ticket 10. What separates these from the list assertions in `test_chats.py` is
that those are about composition being visible in the list at all; these are
about the list being usable at the size a Company actually reaches — hundreds
of threads, found by typing somebody's name, and read a page at a time.
"""

from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from tests.chats import chat_ids, listed, open_chat, open_chat_with
from tests.chat_tokens import bearer, caller_token
from tests.identities import identity_event, now
from tests.messages import say


async def test_the_chat_list_pages_by_cursor(client: AsyncClient):
    """The list pages the way history does, and for the same reason.

    A staff member with hundreds of threads is the case this ticket exists for,
    and a list that answers with all of them is a list that gets slower every
    week. The cursor is the one in `core/cursor.py` — the same opaque pair the
    message pages walk — so there is one pagination contract in this service
    and not two.

    `next_cursor` being null is what "there is no more" means, and it is the
    only thing that says so: a page that came back short is not the same
    statement, because a limit and a remainder can coincide.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)

    chats = []
    for said in ("primeira", "segunda", "terceira"):
        other_id, _ = caller_token()
        chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
        await say(client, chat_id, headers_a, said)
        chats.append(chat_id)
    newest, middle, oldest = reversed(chats)

    first = await listed(client, headers_a, limit=2)
    second = await listed(client, headers_a, limit=2, before=first.json()["next_cursor"])

    assert first.status_code == 200
    assert [chat["id"] for chat in first.json()["chats"]] == [newest, middle]
    assert first.json()["next_cursor"] is not None
    assert [chat["id"] for chat in second.json()["chats"]] == [oldest]
    assert second.json()["next_cursor"] is None


async def test_a_page_landing_exactly_on_the_end_still_says_it_has_ended(
    client: AsyncClient,
):
    """A full page is not a statement that there is more.

    Without the extra row the query fetches and drops, reaching the end and
    landing on it are indistinguishable, and the client is left holding a
    cursor that fetches nothing — with no way to know it has finished until it
    has asked.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    for said in ("uma", "outra"):
        other_id, _ = caller_token()
        chat_id = (await open_chat(client, headers_a, other_id)).json()["id"]
        await say(client, chat_id, headers_a, said)

    exactly_full = await listed(client, headers_a, limit=2)

    assert len(exactly_full.json()["chats"]) == 2
    assert exactly_full.json()["next_cursor"] is None


async def test_a_chat_nobody_has_spoken_in_pages_last(client: AsyncClient):
    """A Chat with no activity sorts behind everything that has any.

    It has to be reachable all the same, and by the cursor rather than by
    falling off the end of it. Ordering by a null activity timestamp is the one
    place the order is not simply "the newest message first", so it is the one
    place a page boundary can silently lose a Chat.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    spoken_in_id = (await open_chat(client, headers_a, caller_token()[0])).json()["id"]
    await say(client, spoken_in_id, headers_a, "oi")
    silent_id = (await open_chat(client, headers_a, caller_token()[0])).json()["id"]

    first = await listed(client, headers_a, limit=1)
    second = await listed(client, headers_a, limit=1, before=first.json()["next_cursor"])

    assert [chat["id"] for chat in first.json()["chats"]] == [spoken_in_id]
    assert [chat["id"] for chat in second.json()["chats"]] == [silent_id]


async def test_two_silent_chats_page_without_skipping_or_repeating(client: AsyncClient):
    """Chats sharing the epoch are separated by the identifier, as messages are.

    Every Chat nobody has spoken in sorts at the same instant, so the activity
    timestamp alone is a partial order and a cursor over a partial order either
    serves a row twice or loses it. The tiebreaker is the Chat's identifier,
    which is the same shape `core/cursor.py` already encodes.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    silent = {
        (await open_chat(client, headers_a, caller_token()[0])).json()["id"]
        for _ in range(3)
    }

    walked: list[str] = []
    cursor = None
    for _ in range(3):
        page = await listed(client, headers_a, limit=1, before=cursor)
        walked += [chat["id"] for chat in page.json()["chats"]]
        cursor = page.json()["next_cursor"]

    assert cursor is None
    assert len(walked) == len(set(walked)) == 3
    assert set(walked) == silent


async def test_a_cursor_this_service_did_not_issue_is_refused(client: AsyncClient):
    """Refused rather than ignored, exactly as the message pages refuse one.

    Falling back to the first page would answer a corrupted scroll position
    with the top of the list and say nothing about it, and a client cannot tell
    that from having genuinely started over.
    """
    _, token_a = caller_token()

    refused = await listed(client, bearer(token_a), before="nao-foi-daqui")

    assert refused.status_code == 422


async def test_the_list_never_walks_a_cursor_into_another_chat_list(
    client: AsyncClient,
):
    """One caller's cursor is a position in their own list and nothing else.

    The pair a cursor names is an activity instant and a Chat identifier, and
    both are real for somebody else's list too. What keeps it from crossing is
    that the participation filter is in the same WHERE clause as the cursor
    comparison, not applied to a page the cursor already chose.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    _, token_b = caller_token()
    headers_b = bearer(token_b)
    for _ in range(2):
        chat_id = (await open_chat(client, headers_a, caller_token()[0])).json()["id"]
        await say(client, chat_id, headers_a, "de A")
    b_chat_id = (await open_chat(client, headers_b, caller_token()[0])).json()["id"]
    await say(client, b_chat_id, headers_b, "de B")

    a_cursor = (await listed(client, headers_a, limit=1)).json()["next_cursor"]

    assert await chat_ids(client, headers_b, before=a_cursor) == []


async def test_the_list_carries_each_chats_last_message(client: AsyncClient):
    """The preview is the message itself, not merely when it arrived.

    A sidebar showing "14:32" and nothing else makes somebody open every Chat
    to find out which one is worth opening. The row is the newest one in the
    Chat's own order, so what the list previews is what the thread opens on.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    chat_id = (await open_chat(client, headers_a, caller_token()[0])).json()["id"]
    await say(client, chat_id, headers_a, "primeira")
    last = await say(client, chat_id, headers_a, "última")

    listed_chat = (await listed(client, headers_a)).json()["chats"][0]

    assert listed_chat["last_message"]["body"] == "última"
    assert listed_chat["last_message"]["id"] == last.json()["id"]
    assert listed_chat["last_message_at"] == last.json()["created_at"]


async def test_a_chat_nobody_has_spoken_in_previews_nothing(client: AsyncClient):
    """Null, and the same null the timestamp already carries.

    A Chat that was composed and never used has no last message, which is a
    different statement from one whose last message has an empty body — that
    second one is a tombstone, and it is a message.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    await open_chat(client, headers_a, caller_token()[0])

    listed_chat = (await listed(client, headers_a)).json()["chats"][0]

    assert listed_chat["last_message"] is None
    assert listed_chat["last_message_at"] is None


async def test_an_end_clients_preview_falls_through_a_staff_only_message(
    client: AsyncClient,
):
    """A Staff-only Message is not the end client's last message — the one below it is.

    This is the checklist line about the list preview, and the failure it
    prevents is subtler than showing the text. Filtering *after* choosing the
    newest row would leave the end client's preview empty while staff saw one,
    which announces the Staff-only Message by the hole it left: the client
    learns something was said that they may not read, which is the one thing
    the rule exists to prevent.
    """
    _, staff_token = caller_token(user_kind="staff")
    end_client_id, end_client_token = caller_token(user_kind="client")
    chat_id = (
        await open_chat(
            client,
            bearer(staff_token),
            end_client_id,
            chat_type="client",
            user_kind="client",
        )
    ).json()["id"]
    visible = await say(client, chat_id, bearer(staff_token), "bom dia")
    await say(client, chat_id, bearer(staff_token), "combinado?", visibility="staff_only")

    by_staff = (await listed(client, bearer(staff_token))).json()["chats"][0]
    by_the_client = (await listed(client, bearer(end_client_token))).json()["chats"][0]

    assert by_staff["last_message"]["body"] == "combinado?"
    assert by_the_client["last_message"]["body"] == "bom dia"
    assert by_the_client["last_message"]["id"] == visible.json()["id"]
    assert by_the_client["last_message_at"] == visible.json()["created_at"]


async def test_the_preview_names_its_sender_rather_than_their_identifier(
    client: AsyncClient,
):
    """The preview is a Message response, so its sender is resolved like any other.

    Resolved from the projection, not from the caller's own token — the whole
    point of the projection is that the list can say who somebody is without
    asking the monolith (ADR-0010).
    """
    sender_id, sender_token = caller_token(display_name="Carla Dias")
    reader_id, reader_token = caller_token(display_name="Bruno Lima")
    chat_id = (await open_chat(client, bearer(sender_token), reader_id)).json()["id"]
    await say(client, chat_id, bearer(sender_token), "bom dia")

    listed_chat = (await listed(client, bearer(reader_token))).json()["chats"][0]

    assert listed_chat["last_message"]["sender_id"] == sender_id
    assert listed_chat["last_message"]["sender_display_name"] == "Carla Dias"


async def test_the_list_filters_by_a_participants_name(client: AsyncClient):
    """The ticket's opening sentence: find the thread by typing who you talked to.

    A substring rather than a whole name, because somebody looking for a thread
    types what they remember — a first name, part of a surname — not the string
    the monolith happens to store.
    """
    _, token_a = caller_token(display_name="Ana Lima")
    headers_a = bearer(token_a)
    bruno_id, _ = caller_token()
    carla_id, _ = caller_token()
    with_bruno = (
        await open_chat_with(client, headers_a, bruno_id, called="Bruno Souza")
    ).json()["id"]
    await open_chat_with(client, headers_a, carla_id, called="Carla Dias")

    assert await chat_ids(client, headers_a, search="souza") == [with_bruno]
    assert await chat_ids(client, headers_a, search="Bru") == [with_bruno]
    assert await chat_ids(client, headers_a, search="Ferreira") == []


async def test_the_filter_also_matches_the_chats_own_name(client: AsyncClient):
    """A group carries a name so it is identifiable in a list, which includes this one.

    Spec item 21 is the reason a group has a name at all. A filter that saw
    only people would make the one thing distinguishing five-person threads
    from each other unsearchable.
    """
    _, token_a = caller_token(display_name="Ana Lima")
    headers_a = bearer(token_a)
    group_id = (
        await open_chat(
            client, headers_a, caller_token()[0], caller_token()[0], name="Enoturismo Sul"
        )
    ).json()["id"]
    await open_chat(client, headers_a, caller_token()[0])

    assert await chat_ids(client, headers_a, search="enoturismo") == [group_id]


async def test_the_filter_ignores_the_callers_own_name(client: AsyncClient):
    """Searching your own name is not a search for every Chat you are in.

    The caller is a Participant of all of them, so matching themselves would
    answer "find the person I was talking to" with the unfiltered list — which
    looks like the filter silently not working.
    """
    _, token_a = caller_token(display_name="Ana Lima")
    headers_a = bearer(token_a)
    bruno_id, _ = caller_token()
    named_after_her = (
        await open_chat_with(client, headers_a, bruno_id, called="Bruno Souza")
    ).json()["id"]

    assert await chat_ids(client, headers_a, search="Ana Lima") == []
    assert await chat_ids(client, headers_a, search="Souza") == [named_after_her]


async def test_the_filter_reads_the_projection_rather_than_the_composition(
    client: AsyncClient,
):
    """A renamed user is found by their new name and not by their old one.

    This is what makes the projection earn its place. The name is not read off
    the command that composed the Chat, nor off anybody's token, nor fetched
    from the monolith when the request arrives (ADR-0010) — it is a column in
    this database, which is the only reason a list filtered by it can be paged
    at all.
    """
    _, token_a = caller_token(display_name="Ana Lima")
    headers_a = bearer(token_a)
    bruno_id, _ = caller_token()
    chat_id = (
        await open_chat_with(client, headers_a, bruno_id, called="Bruno Souza")
    ).json()["id"]

    await identity_event(
        client, bruno_id, display_name="Bruno Ferreira", source_updated_at=now()
    )

    assert await chat_ids(client, headers_a, search="Ferreira") == [chat_id]
    assert await chat_ids(client, headers_a, search="Souza") == []


async def test_the_filtered_list_pages_by_the_same_cursor_contract(client: AsyncClient):
    """A filtered list is a list, and pages like one.

    The checklist line, and the reason the filter had to be a column in this
    database rather than a name resolved per row: a list filtered in Python
    cannot be paged, because the page boundary would have to be decided before
    the filter that decides what is on either side of it.
    """
    _, token_a = caller_token(display_name="Ana Lima")
    headers_a = bearer(token_a)
    matching = []
    for said in ("primeira", "segunda", "terceira"):
        other_id, _ = caller_token()
        chat_id = (
            await open_chat_with(client, headers_a, other_id, called="Bruno Souza")
        ).json()["id"]
        await say(client, chat_id, headers_a, said)
        matching.append(chat_id)
    unmatched_id = (
        await open_chat_with(client, headers_a, caller_token()[0], called="Carla Dias")
    ).json()["id"]
    await say(client, unmatched_id, headers_a, "mais recente que todas")
    newest, middle, oldest = reversed(matching)

    first = await listed(client, headers_a, search="Souza", limit=2)
    second = await listed(
        client, headers_a, search="Souza", limit=2, before=first.json()["next_cursor"]
    )

    assert [chat["id"] for chat in first.json()["chats"]] == [newest, middle]
    assert [chat["id"] for chat in second.json()["chats"]] == [oldest]
    assert second.json()["next_cursor"] is None


async def test_the_filter_ignores_accents_in_both_directions(client: AsyncClient):
    """Brazilian names carry accents and the people searching for them often do not.

    Both directions, because both happen: somebody types "joao" looking for
    João, and somebody types "João" while the monolith stored the name without
    its accent. A filter that matched only the exact spelling would be a search
    box that fails on the most common surnames in the Company's own country,
    and fails silently — an empty list reads as "no such thread".
    """
    _, token_a = caller_token(display_name="Ana Lima")
    headers_a = bearer(token_a)
    accented_id, _ = caller_token()
    plain_id, _ = caller_token()
    accented = (
        await open_chat_with(client, headers_a, accented_id, called="João Conceição")
    ).json()["id"]
    plain = (
        await open_chat_with(client, headers_a, plain_id, called="Joao Assuncao")
    ).json()["id"]

    # As a set: neither Chat has been spoken in, so both sort at the epoch and
    # the tie is broken by an identifier that says nothing about either of them.
    assert set(await chat_ids(client, headers_a, search="joao")) == {plain, accented}
    assert set(await chat_ids(client, headers_a, search="JOÃO")) == {plain, accented}
    assert await chat_ids(client, headers_a, search="conceicao") == [accented]
    assert await chat_ids(client, headers_a, search="Assunção") == [plain]


async def test_the_chats_own_name_is_matched_without_accents_too(client: AsyncClient):
    """The group name goes through the same normalisation as a person's.

    Two halves of one `OR` normalised differently is a filter that finds a
    group by its members' names but not by its own, which nobody would guess
    from the outside.
    """
    _, token_a = caller_token(display_name="Ana Lima")
    headers_a = bearer(token_a)
    group_id = (
        await open_chat(
            client, headers_a, caller_token()[0], caller_token()[0], name="Degustação Sul"
        )
    ).json()["id"]

    assert await chat_ids(client, headers_a, search="degustacao") == [group_id]


async def test_a_wildcard_in_the_search_is_text_and_not_a_pattern(client: AsyncClient):
    """Somebody searching for a name types a name, not a `LIKE` pattern.

    Unescaped, `%` matches the whole list and `_` matches any character — so a
    search returning too much would read as the filter being broken rather than
    as the input being read as a pattern.
    """
    _, token_a = caller_token(display_name="Ana Lima")
    headers_a = bearer(token_a)
    literal_id, _ = caller_token()
    ordinary_id, _ = caller_token()
    literally_named = (
        await open_chat_with(client, headers_a, literal_id, called="Desconto 50% Ltda")
    ).json()["id"]
    await open_chat_with(client, headers_a, ordinary_id, called="Bruno Souza")

    assert await chat_ids(client, headers_a, search="50%") == [literally_named]
    # A lone `%` finds the one name that literally contains one, rather than
    # every Chat in the list — which is what it would mean as a pattern.
    assert await chat_ids(client, headers_a, search="%") == [literally_named]
    assert await chat_ids(client, headers_a, search="Br_no") == []


async def test_the_preview_costs_the_same_whatever_the_list_is_worth(
    client: AsyncClient, db_session: AsyncSession
):
    """The list does not load messages in bulk, which is a line of the ticket.

    Asserted as growth rather than as an absolute: what matters is that a
    Company with three hundred Chats does not pay three hundred round trips to
    show three hundred one-line previews. A `LATERAL` asks the index for one
    row per Chat inside the one query; a relationship prefetch would read every
    Chat's whole history to keep the last row of it, and would do it once per
    page.

    Counting statements is the one place this suite looks at how the service
    works rather than at what it answers, and `.scratch/bwt-chat-microservice/
    spec.md` asks tests not to. The deviation is deliberate and recorded in
    `docs/decisions.md`: the cost *is* the requirement here, it is the kind of
    requirement that regresses in silence — an N+1 list is correct in every
    assertion except the bill — and there is no answer a client can read that
    distinguishes one query from thirty.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)

    async def a_chat_with_a_little_history() -> None:
        chat_id = (await open_chat(client, headers_a, caller_token()[0])).json()["id"]
        for said in ("uma", "outra", "mais uma"):
            await say(client, chat_id, headers_a, said)

    for _ in range(2):
        await a_chat_with_a_little_history()

    engine = db_session.bind.sync_engine
    statements: list[str] = []

    def count_one(_conn, _cursor, statement: str, *_rest: object) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count_one)
    try:
        statements.clear()
        await listed(client, headers_a)
        two_chats = len(statements)
        assert two_chats, "counted nothing, so the comparison below would be vacuous"

        for _ in range(3):
            await a_chat_with_a_little_history()

        statements.clear()
        five_chats = await listed(client, headers_a)
        assert len(five_chats.json()["chats"]) == 5
        assert len(statements) == two_chats
    finally:
        event.remove(engine, "before_cursor_execute", count_one)
