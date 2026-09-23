import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Participant
from tests.chats import open_chat
from tests.chat_tokens import bearer, caller_token


async def test_create_one_to_one_chat(client: AsyncClient):
    user_a_id, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()

    response = await open_chat(client, headers_a, user_b_id)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] is None
    assert set(body["participant_user_ids"]) == {user_a_id, user_b_id}


async def test_create_group_chat(client: AsyncClient):
    user_a_id, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    user_c_id, _ = caller_token()

    response = await open_chat(client, headers_a, user_b_id, user_c_id, name="Trio")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Trio"
    assert set(body["participant_user_ids"]) == {user_a_id, user_b_id, user_c_id}


async def test_create_group_chat_requires_name(client: AsyncClient):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    user_c_id, _ = caller_token()

    response = await open_chat(client, headers_a, user_b_id, user_c_id)

    assert response.status_code == 422


async def test_duplicate_one_to_one_creation_returns_existing_chat(
    client: AsyncClient,
):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()

    first_response = await open_chat(client, headers_a, user_b_id)
    second_response = await open_chat(client, headers_a, user_b_id)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["id"] == second_response.json()["id"]


async def test_one_to_one_creation_ignores_group_with_same_two_members(
    client: AsyncClient,
):
    user_a_id, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    user_c_id, _ = caller_token()

    group_response = await open_chat(client, headers_a, user_b_id, user_c_id, name="Trio 2")
    one_to_one_response = await open_chat(client, headers_a, user_b_id)

    assert group_response.json()["id"] != one_to_one_response.json()["id"]
    assert set(one_to_one_response.json()["participant_user_ids"]) == {
        user_a_id,
        user_b_id,
    }


async def test_list_chats_includes_null_last_message_at_when_no_messages(
    client: AsyncClient,
):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()

    await open_chat(client, headers_a, user_b_id)

    response = await client.get("/chats", headers=headers_a)

    assert response.status_code == 200
    assert response.json()[0]["last_message_at"] is None


async def test_list_chats_reflects_most_recent_message_timestamp(
    client: AsyncClient,
):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()

    create_response = await open_chat(client, headers_a, user_b_id)
    chat_id = create_response.json()["id"]

    send_response = await client.post(
        f"/chats/{chat_id}/messages",
        json={"body": "oi"},
        headers=headers_a,
    )
    message_created_at = send_response.json()["created_at"]

    response = await client.get("/chats", headers=headers_a)

    assert response.status_code == 200
    assert response.json()[0]["last_message_at"] == message_created_at


async def test_list_chats_orders_by_most_recent_message_first(client: AsyncClient):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    user_c_id, _ = caller_token()

    older_response = await open_chat(client, headers_a, user_b_id)
    older_id = older_response.json()["id"]
    await client.post(
        f"/chats/{older_id}/messages",
        json={"body": "mensagem antiga"},
        headers=headers_a,
    )

    no_messages_response = await open_chat(client, headers_a, user_c_id, name="Sem mensagens")
    no_messages_id = no_messages_response.json()["id"]

    newer_response = await open_chat(client, headers_a, user_b_id, user_c_id, name="Recente")
    newer_id = newer_response.json()["id"]
    await client.post(
        f"/chats/{newer_id}/messages",
        json={"body": "mensagem recente"},
        headers=headers_a,
    )

    response = await client.get("/chats", headers=headers_a)

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [newer_id, older_id, no_messages_id]


async def test_list_chats_returns_only_own_chats(client: AsyncClient):
    user_a_id, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, token_b = caller_token()
    headers_b = bearer(token_b)
    _, token_c = caller_token()
    headers_c = bearer(token_c)

    shared_response = await open_chat(client, headers_a, user_b_id)
    shared_chat_id = shared_response.json()["id"]

    await open_chat(client, headers_c, user_a_id)

    response = await client.get("/chats", headers=headers_b)

    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body] == [shared_chat_id]


async def test_create_chat_records_the_type_it_was_opened_as(client: AsyncClient):
    _, token_a = caller_token(user_kind="staff")
    user_b_id, _ = caller_token()
    user_c_id, _ = caller_token()

    staff = await open_chat(client, bearer(token_a), user_b_id)
    client_chat = await open_chat(
        client, bearer(token_a), user_c_id, chat_type="client", user_kind="client"
    )

    assert (staff.status_code, client_chat.status_code) == (201, 201)
    assert staff.json()["type"] == "staff"
    assert client_chat.json()["type"] == "client"


async def test_staff_chat_containing_an_end_client_is_rejected(client: AsyncClient):
    """The shape of a Chat is the service's own business, not the caller's.

    A Staff Chat is defined by the absence of the end client. Accepting one
    with a client inside would not fail here — it would fail later, silently,
    the first time ticket 04's visibility rule read the Chat's type and
    concluded there was nobody to hide a Staff-only Message from.

    The Client Chat alongside it is the control: what is refused is this Chat's
    shape, not this pair of people.
    """
    _, token_staff = caller_token(user_kind="staff")
    end_client_id, _ = caller_token(user_kind="client")

    refused = await open_chat(client, bearer(token_staff), end_client_id, user_kind="client")
    allowed = await open_chat(
        client, bearer(token_staff), end_client_id, chat_type="client", user_kind="client"
    )

    assert refused.status_code == 422
    assert allowed.status_code == 201


async def test_an_end_client_cannot_open_a_staff_chat(client: AsyncClient):
    """The caller is in the Chat too, and the token says which kind they are.

    Checking only the named Participants would let the one person the rule is
    about walk in through the door they opened themselves.
    """
    _, token_end_client = caller_token(user_kind="client")
    colleague_id, _ = caller_token(user_kind="staff")

    refused = await open_chat(
        client, bearer(token_end_client), colleague_id, user_kind="staff"
    )

    assert refused.status_code == 422


async def test_a_caller_whose_kind_is_unrecognised_cannot_be_placed_in_a_chat(
    client: AsyncClient,
):
    """A user kind the service does not know is a refusal, not a crash.

    The monolith owns the vocabulary of user kinds and may widen it without
    asking. Anything outside `staff` and `client` has no place in a Chat whose
    rules are written in those two words, so the command fails to the narrow
    side — the same default-deny the spec asks of ticket 04's predicate, for
    the same reason it names: an unrecognised kind is how the source module's
    staff-only rule went wrong.

    Note this is not how a Supervisor arrives. Supervision is a scope on an
    ordinary staff token (ticket 13), not a third user kind.
    """
    _, token = caller_token(user_kind="brand-partner")
    other_id, _ = caller_token()

    response = await open_chat(client, bearer(token), other_id)

    assert response.status_code == 422


async def _record_departure(db: AsyncSession, chat_id: str, user_id: str) -> Participant:
    """Mark a Participant as having left, the way ticket 05's command will.

    There is no endpoint for this yet, and inventing one to test the read paths
    would be building the wrong half of ticket 05. What is under test is what
    every read means by "a current Participant", so the departure is recorded
    directly and the reads are driven through the API.
    """
    participant = await db.scalar(
        select(Participant).where(
            Participant.chat_id == uuid.UUID(chat_id),
            Participant.user_id == uuid.UUID(user_id),
        )
    )
    assert participant is not None
    participant.left_at = datetime.now(timezone.utc)
    await db.commit()
    return participant


async def test_a_participant_who_left_is_no_longer_a_current_participant(
    client: AsyncClient, db_session: AsyncSession
):
    user_a_id, token_a = caller_token()
    user_b_id, token_b = caller_token()
    chat_id = (await open_chat(client, bearer(token_a), user_b_id)).json()["id"]

    departed = await _record_departure(db_session, chat_id, user_b_id)

    still_in = await client.get("/chats", headers=bearer(token_a))
    left = await client.get("/chats", headers=bearer(token_b))
    reading_after_leaving = await client.get(f"/chats/{chat_id}/messages", headers=bearer(token_b))
    writing_after_leaving = await client.post(
        f"/chats/{chat_id}/messages", json={"body": "ainda aqui?"}, headers=bearer(token_b)
    )

    assert still_in.json()[0]["participant_user_ids"] == [user_a_id]
    assert left.json() == []
    assert reading_after_leaving.status_code == 404
    assert writing_after_leaving.status_code == 404
    assert departed.id is not None, "the row stays; only the membership ended"


async def test_reopening_a_one_to_one_someone_left_does_not_return_the_old_chat(
    client: AsyncClient, db_session: AsyncSession
):
    """A Chat nobody is left in is not the Chat the caller is asking to open.

    Handing back the old one would silently re-add a Participant who left,
    which is the one thing recording the departure was meant to prevent.
    """
    _, token_a = caller_token()
    user_b_id, _ = caller_token()
    first_id = (await open_chat(client, bearer(token_a), user_b_id)).json()["id"]

    await _record_departure(db_session, first_id, user_b_id)
    reopened = await open_chat(client, bearer(token_a), user_b_id)

    assert reopened.status_code == 201
    assert reopened.json()["id"] != first_id


async def test_opening_a_one_to_one_of_another_type_does_not_reuse_the_existing_chat(
    client: AsyncClient,
):
    """Idempotency is about the Chat asked for, not about the pair of people.

    Handing back a Staff Chat to someone who asked for a Client Chat answers a
    question nobody put, and the response says so — it carries a `type` the
    caller did not request.
    """
    _, token_a = caller_token()
    user_b_id, _ = caller_token()

    staff = await open_chat(client, bearer(token_a), user_b_id)
    client_chat = await open_chat(client, bearer(token_a), user_b_id, chat_type="client")
    staff_again = await open_chat(client, bearer(token_a), user_b_id)

    assert client_chat.json()["id"] != staff.json()["id"]
    assert client_chat.json()["type"] == "client"
    assert staff_again.json()["id"] == staff.json()["id"]
