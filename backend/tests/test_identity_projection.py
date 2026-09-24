"""The identity projection: names the service knows without asking for them.

ADR-0010 forbids a request path that calls the monolith, so a display name
cannot be fetched when a response is built. It has to already be here. Three
inbound writes put it here — the identity inside a composition command, an
identity event, and a bulk load — and every one of them is idempotent, because
all three arrive at-least-once.

What these tests never do is assert the projection by reading its table. The
projection is only worth anything through what it makes a response say, so the
rule it has to keep — a message shows the sender's name as the monolith last
described it, to a reader who has never held that name themselves — is asserted
where a client can see it.
"""

import re
import uuid
from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Base
from app.services.projection_health import projection_lag
from tests.chats import acting_for, identity, open_chat
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token
from tests.messages import say
from tests.identities import (
    a_chat_with_one_message,
    bulk_load,
    identity_event,
    naive_now,
    now,
    snapshot,
)


async def test_a_message_shows_the_sender_s_name_to_a_reader_who_never_held_it(
    client: AsyncClient,
):
    """The name comes from the projection, and it cannot have come from anywhere else.

    B reads a message A sent. B's own token carries B's name and says nothing
    about A, and no message row stores a name — so the only way `Carla Dias`
    reaches this response is the profile the composition command wrote.
    """
    _, read_by_b = await a_chat_with_one_message(client)

    assert await read_by_b() == ["Carla Dias"]


async def test_an_identity_event_reaches_messages_already_sent(client: AsyncClient):
    """Anonymisation in the monolith reaches chat history, and costs one row to do it.

    No message table stores a name, so rewriting the profile rewrites every
    message that user ever sent — which is what makes this reachable without
    the service knowing what a data-protection law is. Denormalising the name
    onto the message "to save a join" is what would break it, silently and only
    for history.
    """
    user_a_id, read_by_b = await a_chat_with_one_message(client)

    accepted = await identity_event(
        client, user_a_id, display_name="Usuário removido", source_updated_at=now()
    )

    assert accepted.status_code == 204
    assert await read_by_b() == [
        "Usuário removido"
    ]


async def test_an_event_that_arrives_late_does_not_reinstate_the_name_it_carried(
    client: AsyncClient,
):
    """Out of order is the normal case, not the exceptional one.

    At-least-once delivery says nothing about order, so the stream will
    redeliver a week-old event after a fresh one at some point. Ordering by
    arrival would make that a name coming back from the dead — visible to
    everyone, reproducible by nobody. `source_updated_at` is the monolith's
    clock, and it is what decides.
    """
    user_a_id, read_by_b = await a_chat_with_one_message(client)

    await identity_event(
        client, user_a_id, display_name="Carla Nogueira", source_updated_at=now()
    )
    late = await identity_event(
        client,
        user_a_id,
        display_name="Carla Dias",
        source_updated_at=now() - timedelta(hours=1),
    )

    assert late.status_code == 204
    assert await read_by_b() == [
        "Carla Nogueira"
    ]


async def test_a_bulk_load_replaces_what_a_composition_command_left_behind(
    client: AsyncClient,
):
    """The rebuild path, and why the command's write has to be the weakest one.

    A command carries an identity but no timestamp for it, so its row is
    undated. A bulk load is the monolith stating what is true right now, dated
    — so it wins, and a corrupted or newly created projection can be refilled
    without replaying the whole event history.
    """
    user_a_id, read_by_b = await a_chat_with_one_message(client)

    loaded = await bulk_load(
        client, snapshot(user_a_id, display_name="Carla Nogueira", source_updated_at=now())
    )

    assert loaded.status_code == 204
    assert await read_by_b() == [
        "Carla Nogueira"
    ]


async def test_a_bulk_load_naming_the_same_user_twice_keeps_the_newest(
    client: AsyncClient,
):
    """A rebuild is assembled by somebody else, and arrives however it arrives.

    A full reload is the one write that plausibly carries a user more than
    once — two pages stitched together, or a user changed while the export ran.
    Postgres refuses to let a single statement touch the same row twice, so
    without a rule the whole load fails, and it fails on exactly the input
    nobody tests a rebuild with.
    """
    user_a_id, read_by_b = await a_chat_with_one_message(client)

    loaded = await bulk_load(
        client,
        snapshot(
            user_a_id,
            display_name="Carla Dias",
            source_updated_at=now() - timedelta(hours=1),
        ),
        snapshot(user_a_id, display_name="Carla Nogueira", source_updated_at=now()),
    )

    assert loaded.status_code == 204
    assert await read_by_b() == [
        "Carla Nogueira"
    ]


async def test_adding_a_participant_teaches_the_projection_their_name(
    client: AsyncClient,
):
    """Every composition command is a write, not only the one that opens the Chat.

    Whoever joins reads everything said since the Chat was created and starts
    saying things of their own, so a join that taught the projection nothing
    would leave a Participant whose messages are signed by nobody — for every
    reader, until some unrelated identity event happened to mention them.
    """
    user_a_id, token_a = caller_token(display_name="Carla Dias")
    user_b_id, token_b = caller_token(display_name="Bruno Lima")
    user_c_id, token_c = caller_token(display_name="Ana Souza")

    chat_id = (await open_chat(client, bearer(token_a), user_b_id)).json()["id"]
    joined = await client.post(
        f"/internal/chats/{chat_id}/participants",
        json={
            "participant": identity(user_c_id, display_name="Diego Alves"),
            "name": "Operação",
        },
        headers=acting_for(user_a_id, str(DEFAULT_COMPANY_ID)),
    )
    await say(client, chat_id, bearer(token_c), "cheguei")

    read_by_b = await client.get(f"/chats/{chat_id}/messages", headers=bearer(token_b))

    assert joined.status_code == 200
    assert [message["sender_display_name"] for message in read_by_b.json()["messages"]] == [
        "Diego Alves"
    ]


async def test_projection_lag_is_the_widest_gap_between_the_source_and_this_service(
    client: AsyncClient, db_session: AsyncSession
):
    """The one health signal this projection has, because it has no miss path.

    There is no cache hit rate to watch: nothing ever fetches an identity it
    does not hold, so a stalled stream is invisible from inside — every
    response keeps answering, promptly, with a name that is quietly months old.
    The gap between when the monolith changed an identity and when this service
    wrote it is the only thing that shows it, and the *widest* gap is the one
    that matters, because a single stuck user is what a mean would hide.
    """
    user_a_id, token_a = caller_token()
    user_b_id, _ = caller_token()
    await open_chat(client, bearer(token_a), user_b_id)

    fresh = await projection_lag(db_session)
    await identity_event(
        client,
        user_a_id,
        display_name="Carla Nogueira",
        source_updated_at=now() - timedelta(hours=3),
    )
    behind = await projection_lag(db_session)

    assert fresh is None
    assert behind is not None and behind >= timedelta(hours=3)


def test_no_message_table_stores_a_name_an_email_or_an_avatar():
    """The invariant the whole projection rests on, checked against the schema.

    Resolving the sender's name at build time costs a join, and the join is
    what makes an anonymisation in the monolith reach chat history: one profile
    row is rewritten and every message that user ever sent is signed
    differently. Copying the name onto the message "to save a join" breaks that
    silently and only for the past — new messages look right, history keeps the
    name of somebody who asked to be forgotten, and no test fails.

    Message tables are found rather than listed, so the attachment or reaction
    table somebody adds next is covered the moment it is mapped, instead of
    having to be remembered here.
    """
    import app.models  # noqa: F401 - mapping every model is the point

    denormalised = re.compile(r"name|email|avatar", re.IGNORECASE)
    message_tables = [
        mapper.class_.__table__
        for mapper in Base.registry.mappers
        if "message" in mapper.class_.__table__.name
    ]
    offending = [
        f"{table.name}.{column.name}"
        for table in message_tables
        for column in table.columns
        if denormalised.search(column.name)
    ]

    assert message_tables, "found no message tables, so an empty list would mean nothing"
    assert offending == [], (
        "these copy an identity onto a message instead of resolving it: "
        + ", ".join(offending)
    )


async def test_an_identity_whose_timestamp_has_no_timezone_is_refused(
    client: AsyncClient,
):
    """`source_updated_at` is the ordering rule, so an ambiguous one is not usable.

    A naive timestamp does not say which clock it came from. Stored into a
    `timestamptz` column it is read as the database server's zone, which shifts
    it by hours and silently reorders events against each other — and compared
    in Python against an aware one it raises, which turns a whole bulk load
    into a 500. Refusing at the door is the only answer that cannot be wrong
    later: the monolith is told to fix its emitter while the projection is
    still correct.
    """
    user_a_id, _ = caller_token()

    refused = await identity_event(
        client, user_a_id, display_name="Carla Nogueira", source_updated_at=naive_now()
    )
    load_refused = await bulk_load(
        client,
        snapshot(user_a_id, display_name="Carla Nogueira", source_updated_at=naive_now()),
    )

    assert refused.status_code == 422
    assert load_refused.status_code == 422


async def test_replaying_an_event_writes_nothing_at_all(
    client: AsyncClient, db_session: AsyncSession
):
    """What closes the "deduplicated by event id" criterion without a table for it.

    The service keeps no record of the event ids it has seen. It does not need
    one: a redelivery carries the timestamp it carried the first time, and the
    comparison is strict, so an equal `source_updated_at` loses exactly as an
    older one does. That clause is the whole of the argument, so it is the
    thing that has to be tested — and it is observable, because a write would
    move `synced_at` forward while the source timestamp stayed put, which is
    the projection's lag growing for a redelivery that changed nothing.

    When this ingress grows work that is not idempotent by construction — an
    outbox row on the way out, which is ticket 15 — the timestamp stops
    covering it and a table of seen ids becomes load-bearing.
    """
    user_a_id, _ = caller_token()
    delivered = {
        "display_name": "Carla Nogueira",
        "source_updated_at": now() - timedelta(hours=3),
        "event_id": str(uuid.uuid4()),
    }

    await identity_event(client, user_a_id, **delivered)
    after_first = await projection_lag(db_session)
    await identity_event(client, user_a_id, **delivered)
    after_replay = await projection_lag(db_session)

    assert after_first is not None
    assert after_replay == after_first
