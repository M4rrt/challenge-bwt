"""Composition as a command, driven the way the monolith drives it.

Creating a Chat and adding or removing a Participant are no longer things a
browser asks the service to do. The monolith validates them against live data —
Company membership, active status, and for an end client the CRM contact
relation that cannot be mirrored — and then calls these routes with a service
credential and headers naming the user it is acting for.

ADR-0010 is what these tests hold up: no request path of the service queries the
monolith, and the service does not re-check what whoever signed the command is
the authority on. What it does check is the shape of the Chat, which is its own
business.
"""

import ast
import uuid
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.chat import Chat
from app.models.outbox import OutboxEvent
from app.services.outbox import drain_once

from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token
from tests.chats import acting_for, identity, service_credential
from tests.messages import say


async def _command(
    client: AsyncClient,
    *participants: dict[str, object],
    acting_user_id: str,
    company_id: str = str(DEFAULT_COMPANY_ID),
    chat_type: str = "staff",
    name: str | None = None,
    headers: dict[str, str] | None = None,
):
    return await client.post(
        "/internal/chats",
        json={"type": chat_type, "name": name, "participants": list(participants)},
        headers=acting_for(acting_user_id, company_id) if headers is None else headers,
    )


async def test_a_chat_token_is_not_a_service_credential(client: AsyncClient):
    """The two vocabularies of "who is calling" do not overlap.

    A chat token is what an end client's browser holds. If it opened the
    internal routes, every rule the monolith validates against live data would
    be back in the hands of whoever holds a fifteen-minute token.
    """
    actor_id, token = caller_token()

    response = await _command(
        client,
        identity(actor_id),
        acting_user_id=actor_id,
        headers=bearer(token)
        | {"X-Acting-User": actor_id, "X-Acting-Company": str(DEFAULT_COMPANY_ID)},
    )

    assert response.status_code == 401


async def test_a_command_naming_no_acting_user_is_refused(client: AsyncClient):
    """There is no Chat without an author, so the header is a refusal and not a default.

    This is what stops the service credential becoming an omnipotent one: it
    does not widen what can be done, it only allows doing it on behalf of
    someone identified.
    """
    actor_id = str(uuid.uuid4())

    unnamed = await _command(
        client, identity(actor_id), acting_user_id=actor_id, headers=service_credential()
    )
    no_company = await _command(
        client,
        identity(actor_id),
        acting_user_id=actor_id,
        headers=service_credential() | {"X-Acting-User": actor_id},
    )

    assert (unnamed.status_code, no_company.status_code) == (401, 401)


async def test_the_command_creates_a_chat_of_exactly_the_participants_it_carries(
    client: AsyncClient,
):
    """The command names everyone, and the service adds nobody.

    The monolith had every Participant's identity in hand to validate them, so
    sending it along costs nothing and removes the one case that would force
    the service to ask back.
    """
    actor_id, _ = caller_token()
    other_id, other_token = caller_token()

    created = await _command(
        client, identity(actor_id), identity(other_id), acting_user_id=actor_id
    )
    listed_by_the_other = await client.get("/chats", headers=bearer(other_token))

    assert created.status_code == 201
    assert set(created.json()["participant_user_ids"]) == {actor_id, other_id}
    assert [chat["id"] for chat in listed_by_the_other.json()] == [created.json()["id"]]


async def test_a_command_naming_a_participant_from_another_company_is_refused(
    client: AsyncClient,
):
    """A Chat and its Participants answer to the same boundary, or the command fails.

    The command carries each Participant's Company because the monolith had it
    in hand; the service files them under the Company it was asked to act for.
    Letting those differ would put a Chat's members outside the Chat's own
    boundary, and every read that joins the two would cross it.
    """
    actor_id = str(uuid.uuid4())
    outsider = identity(str(uuid.uuid4()), company_id=str(uuid.uuid4()))

    response = await _command(
        client, identity(actor_id), outsider, acting_user_id=actor_id
    )

    assert response.status_code == 422


async def test_a_participant_whose_kind_is_unrecognised_is_refused(client: AsyncClient):
    """A user kind the service does not know is a refusal, not a crash.

    The monolith owns the vocabulary of user kinds and may widen it without
    asking. Anything outside `staff` and `client` has no place in a Chat whose
    rules are written in those two words, so the command fails to the narrow
    side.
    """
    actor_id = str(uuid.uuid4())

    response = await _command(
        client,
        identity(actor_id),
        identity(str(uuid.uuid4()), "brand-partner"),
        acting_user_id=actor_id,
    )

    assert response.status_code == 422


async def test_the_command_must_carry_each_participants_display_name(client: AsyncClient):
    """The identity travels with the identifier, and travelling is not optional.

    The service has no user table and may not ask the monolith back, so a
    command that names an identifier alone describes somebody the service could
    never render. Ticket 06 is what stores this; refusing it now is what keeps
    that from being a change to the wire contract.
    """
    actor_id = str(uuid.uuid4())
    nameless = identity(actor_id)
    del nameless["display_name"]

    response = await _command(client, nameless, acting_user_id=actor_id)

    assert response.status_code == 422


async def test_no_public_endpoint_creates_a_chat(client: AsyncClient):
    """Composition left the public surface entirely, and did not merely move.

    A chat token is held by a browser, including an end client's. If it could
    still open a Chat or add somebody to one, every validation the monolith
    performs against live data — Company membership, active status, the CRM
    contact relation — would be a suggestion.
    """
    _, token = caller_token()

    created = await client.post(
        "/chats",
        json={"type": "staff", "participants": [], "name": None},
        headers=bearer(token),
    )

    assert created.status_code in (404, 405)


async def _add(
    client: AsyncClient,
    chat_id: str,
    participant: dict[str, object],
    *,
    acting_user_id: str,
    company_id: str = str(DEFAULT_COMPANY_ID),
    name: str | None = None,
):
    return await client.post(
        f"/internal/chats/{chat_id}/participants",
        json={"participant": participant, "name": name},
        headers=acting_for(acting_user_id, company_id),
    )


async def test_adding_a_participant_puts_them_in_the_chat(client: AsyncClient):
    """Story 18: bring in whoever the Chat now needs.

    The Chat becomes a group as it happens, so the command carries the name the
    group rule asks for — the alternative is a refusal followed by a rename,
    which is two commands for one act of composition.
    """
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    third_id, third_token = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    added = await _add(client, chat_id, identity(third_id), acting_user_id=actor_id, name="Trio")
    listed_by_the_third = await client.get("/chats", headers=bearer(third_token))

    assert added.status_code == 200
    assert set(added.json()["participant_user_ids"]) == {actor_id, other_id, third_id}
    assert [chat["id"] for chat in listed_by_the_third.json()] == [chat_id]


async def test_adding_an_end_client_to_a_staff_chat_is_refused(client: AsyncClient):
    """The shape of a Chat is a property of the Chat, not of the moment it was reached.

    A Staff Chat is defined by the absence of the end client. Checked only on
    creation, the rule would have a way around it — open the Staff Chat, then
    add the client — and ticket 04's visibility rule would then read a Chat
    whose type says there is nobody to hide a Staff-only Message from.
    """
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    refused = await _add(
        client,
        chat_id,
        identity(str(uuid.uuid4()), "client"),
        acting_user_id=actor_id,
        name="Trio",
    )

    assert refused.status_code == 422


async def test_a_third_participant_needs_the_chat_to_have_a_name(client: AsyncClient):
    """The same rule as on creation, for the same reason: an unnamed group is unidentifiable."""
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    refused = await _add(client, chat_id, identity(str(uuid.uuid4())), acting_user_id=actor_id)

    assert refused.status_code == 422


async def test_adding_someone_already_in_the_chat_changes_nothing(client: AsyncClient):
    """Commands arrive at-least-once, so a repeat is the command having already succeeded."""
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    repeated = await _add(client, chat_id, identity(other_id), acting_user_id=actor_id)

    assert repeated.status_code == 200
    assert set(repeated.json()["participant_user_ids"]) == {actor_id, other_id}


async def test_a_command_for_another_companys_chat_finds_nothing(client: AsyncClient):
    """The boundary answers a command the way it answers a read: the Chat is absent.

    The monolith holds the service credential, so this is not a defence against
    it — it is the same 404-not-403 decision every other path makes, so that a
    bug on the far side cannot compose across Companies by accident.
    """
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]
    elsewhere = str(uuid.uuid4())

    refused = await _add(
        client,
        chat_id,
        identity(str(uuid.uuid4()), company_id=elsewhere),
        acting_user_id=actor_id,
        company_id=elsewhere,
        name="Trio",
    )

    assert refused.status_code == 404


async def _remove(
    client: AsyncClient,
    chat_id: str,
    user_id: str,
    *,
    acting_user_id: str,
    company_id: str = str(DEFAULT_COMPANY_ID),
):
    return await client.request(
        "DELETE",
        f"/internal/chats/{chat_id}/participants/{user_id}",
        headers=acting_for(acting_user_id, company_id),
    )


async def test_removing_a_participant_takes_them_out_of_the_chat(client: AsyncClient):
    """Stories 19 and 20: someone stops being in a Chat, whoever decided it.

    Leaving and being removed are one command, because the difference between
    them is who the monolith is acting for — and it is the monolith, not the
    service, that knows whether that person was allowed to decide.
    """
    actor_id, actor_token = caller_token()
    other_id, other_token = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]
    await say(client, chat_id, bearer(other_token), "até mais")

    removed = await _remove(client, chat_id, other_id, acting_user_id=actor_id)

    listed_by_the_removed = await client.get("/chats", headers=bearer(other_token))
    read_after_removal = await client.get(f"/chats/{chat_id}/messages", headers=bearer(other_token))
    still_read_by_the_rest = await client.get(
        f"/chats/{chat_id}/messages", headers=bearer(actor_token)
    )

    assert removed.status_code == 200
    assert removed.json()["participant_user_ids"] == [actor_id]
    assert listed_by_the_removed.json() == []
    assert read_after_removal.status_code == 404
    assert [message["body"] for message in still_read_by_the_rest.json()] == ["até mais"]


async def test_removing_someone_twice_does_not_move_when_they_left(client: AsyncClient):
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    first = await _remove(client, chat_id, other_id, acting_user_id=actor_id)
    repeated = await _remove(client, chat_id, other_id, acting_user_id=actor_id)

    assert (first.status_code, repeated.status_code) == (200, 200)
    assert repeated.json()["participant_user_ids"] == [actor_id]


async def test_removing_someone_who_was_never_in_the_chat_finds_nothing(client: AsyncClient):
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    refused = await _remove(client, chat_id, str(uuid.uuid4()), acting_user_id=actor_id)

    assert refused.status_code == 404


async def test_someone_removed_can_be_put_back_and_reads_what_was_said_meanwhile(
    client: AsyncClient,
):
    """Whoever joins reads everything said since the Chat was created.

    Leaving is recorded on the row rather than by deleting it, so putting
    somebody back revives that row instead of making a second one — which is
    also the only reading the unique constraint on (Chat, user) allows.
    """
    actor_id, actor_token = caller_token()
    other_id, other_token = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]
    await _remove(client, chat_id, other_id, acting_user_id=actor_id)
    await say(client, chat_id, bearer(actor_token), "enquanto isso")

    back = await _add(client, chat_id, identity(other_id), acting_user_id=actor_id)
    read_after_returning = await client.get(
        f"/chats/{chat_id}/messages", headers=bearer(other_token)
    )

    assert back.status_code == 200
    assert set(back.json()["participant_user_ids"]) == {actor_id, other_id}
    assert [message["body"] for message in read_after_returning.json()] == ["enquanto isso"]


async def test_every_command_route_refuses_without_the_service_credential(client: AsyncClient):
    """The credential guards the ingress, not the one route somebody remembered.

    The network is supposed to keep these off the public internet. This is the
    second lock, for the day a load balancer rule is written wider than it was
    meant to be.
    """
    chat_id, user_id = str(uuid.uuid4()), str(uuid.uuid4())

    unauthenticated = [
        await client.post("/internal/chats", json={"type": "staff", "participants": []}),
        await client.post(
            f"/internal/chats/{chat_id}/participants",
            json={"participant": identity(user_id), "name": None},
        ),
        await client.request("DELETE", f"/internal/chats/{chat_id}/participants/{user_id}"),
    ]

    assert [response.status_code for response in unauthenticated] == [401, 401, 401]


async def test_the_service_lists_nobody_who_may_participate(client: AsyncClient):
    """Who is a client of a Company is a CRM fact, and it stays in the monolith.

    ADR-0010 names this as the "no" that is easy to undo without understanding:
    somebody will propose bringing the list here so the interface talks to one
    origin. Mirroring it would mean mirroring the contact book and its churn,
    and the staleness would land on the one operation where it hurts most —
    whoever joins a Chat reads everything said in it since it was created.
    """
    _, token = caller_token()

    # Asked of the published surface rather than of `app.routes`, which does
    # not flatten an included router and would have let every one of these
    # through while looking like it had checked.
    directories = sorted(
        path
        for path, methods in app.openapi()["paths"].items()
        if "get" in methods and path.rstrip("/").rsplit("/", 1)[-1] in ("users", "participants")
    )
    asked_anyway = await client.get("/users", headers=bearer(token))
    asked_with_the_credential = await client.get("/internal/users", headers=service_credential())

    assert directories == []
    assert (asked_anyway.status_code, asked_with_the_credential.status_code) == (404, 404)


def test_no_module_of_the_service_holds_an_http_client():
    """No request path of the service queries the monolith — structurally, not by habit.

    ADR-0010's guarantee is a negative one, and a negative is kept by nothing
    existing: the moment an HTTP client is in here, the first "just ask the
    monolith whether this user is still active" is one line away, and it will
    be written inside a request where the monolith being slow becomes the chat
    being slow.

    Outbound traffic is not forbidden — events flow that way — but it flows
    from the drain, asynchronously, out of the request. A module that needs a
    client for that should appear here as an exemption with its reason, the way
    `tests/test_company_isolation.py` exempts the drain's read of the outbox,
    rather than quietly widening what a request may do.
    """
    clients = {"httpx", "requests", "aiohttp", "urllib", "urllib3", "http"}
    application = Path(__file__).resolve().parent.parent / "app"
    offenders: list[str] = []

    for source in sorted(application.rglob("*.py")):
        for node in ast.walk(ast.parse(source.read_text())):
            imported = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(name.split(".")[0] in clients for name in imported):
                offenders.append(f"{source.relative_to(application.parent)}:{node.lineno}")

    assert offenders == [], (
        "these could call the monolith from inside a request: " + ", ".join(offenders)
    )


async def test_a_command_naming_nobody_is_refused(client: AsyncClient):
    """A Chat with no Participants is a row no read path can ever reach.

    The service used to be spared this: the caller was added from their own
    token, so a Chat always had at least the person who opened it. Now the
    command names everyone and the service adds nobody, which means it also has
    to say that naming nobody is not composition.
    """
    actor_id = str(uuid.uuid4())

    response = await _command(client, acting_user_id=actor_id)

    assert response.status_code == 422


async def test_a_redelivered_add_announces_nothing(
    client: AsyncClient, db_session: AsyncSession
):
    """At-least-once means the same command lands twice, and the second is silent.

    Every Participant's chat list is pushed when a Chat's composition changes.
    A redelivery that changes nothing and pushes anyway would move every open
    list for no reason — and the drain would carry it, so this is noise all the
    way to the socket.
    """
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]
    await drain_once(db_session)

    await _add(client, chat_id, identity(other_id), acting_user_id=actor_id)
    pending = await db_session.scalars(
        select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
    )

    assert list(pending) == []


async def test_a_redelivered_add_does_not_name_a_one_to_one(client: AsyncClient):
    """The name answers the group rule; it does not rename what is already there.

    A command carrying a name for a Chat that stays a 1:1 has nothing to
    answer, and adopting it anyway would let a redelivery — the same command
    arriving twice — put a name on a Chat nobody asked to name.
    """
    actor_id, _ = caller_token()
    other_id, _ = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    repeated = await _add(
        client, chat_id, identity(other_id), acting_user_id=actor_id, name="Trio"
    )

    assert repeated.status_code == 200
    assert repeated.json()["name"] is None


async def test_composition_failing_leaves_existing_chats_sending_and_receiving(
    client: AsyncClient,
):
    """The degradation profile that justifies the extraction, asserted rather than assumed.

    Monolith down means no new Chats and no new Participants. It does not mean a
    quiet chat: everything already composed keeps working, because nothing on
    the send or read path has the monolith in it. Here the command fails the way
    it fails when the far side cannot sign it, and the Chat carries on.
    """
    actor_id, actor_token = caller_token()
    other_id, other_token = caller_token()
    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    composition = await client.post(
        "/internal/chats",
        json={"type": "staff", "name": None, "participants": [identity(actor_id)]},
        headers={"X-Acting-User": actor_id, "X-Acting-Company": str(DEFAULT_COMPANY_ID)},
    )
    sent = await say(client, chat_id, bearer(actor_token), "seguimos")
    read = await client.get(f"/chats/{chat_id}/messages", headers=bearer(other_token))

    assert composition.status_code == 401
    assert sent.status_code == 201
    assert [message["body"] for message in read.json()] == ["seguimos"]


async def test_the_chat_records_the_user_it_was_composed_for(
    client: AsyncClient, db_session: AsyncSession
):
    """There is no Chat without an author, and the author leaves a trace.

    The header is what stops the service credential being usable on nobody's
    behalf; the column is what makes that answerable afterwards. Asserted on
    the row rather than through a response because nothing renders it — it is
    there for whoever asks later who opened this.
    """
    actor_id, _ = caller_token()
    other_id, _ = caller_token()

    chat_id = (
        await _command(client, identity(actor_id), identity(other_id), acting_user_id=actor_id)
    ).json()["id"]

    composed = await db_session.scalar(select(Chat).where(Chat.id == uuid.UUID(chat_id)))

    assert composed is not None
    assert composed.created_by_user_id == uuid.UUID(actor_id)
