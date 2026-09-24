import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.models.chat import Chat, ChatType, Participant, ParticipantRole
from app.schemas.message import MessageCreate
from app.services.message import ChatNotFoundError, list_messages, send_message
from tests.chats import open_chat_id, open_chat_of
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token, make_caller
from tests.messages import bodies, say


async def _create_chat(db: AsyncSession, *user_ids: uuid.UUID) -> Chat:
    chat = Chat(company_id=DEFAULT_COMPANY_ID, type=ChatType.STAFF, name=None)
    chat.participants = [
        Participant(company_id=DEFAULT_COMPANY_ID, user_id=uid, role=ParticipantRole.STAFF)
        for uid in user_ids
    ]
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


async def _send(db: AsyncSession, caller: Caller, chat_id: uuid.UUID, body: str):
    """Call the service the way the router does — with the scope its dependency injects."""
    scope = CompanyScope.of(caller)
    return await send_message(
        db, scope, caller, chat_id, MessageCreate(body=body, client_message_id=uuid.uuid4().hex)
    )


async def _list(db: AsyncSession, caller: Caller, chat_id: uuid.UUID):
    return await list_messages(db, CompanyScope.of(caller), caller, chat_id)


async def test_participant_can_send_message(db_session: AsyncSession):
    sender = make_caller()
    other = make_caller()
    chat = await _create_chat(db_session, sender.id, other.id)

    message = await _send(db_session, sender, chat.id, "oi")

    assert message.body == "oi"
    assert message.chat_id == chat.id
    assert message.sender_id == sender.id
    assert message.sender_type == "user"


async def test_non_participant_cannot_send_message(db_session: AsyncSession):
    sender = make_caller()
    other = make_caller()
    outsider = make_caller()
    chat = await _create_chat(db_session, sender.id, other.id)

    with pytest.raises(ChatNotFoundError):
        await _send(db_session, outsider, chat.id, "oi")


async def test_participant_can_list_messages_in_order(db_session: AsyncSession):
    sender = make_caller()
    other = make_caller()
    chat = await _create_chat(db_session, sender.id, other.id)

    first = await _send(db_session, sender, chat.id, "first")
    second = await _send(db_session, other, chat.id, "second")

    messages = await _list(db_session, sender, chat.id)

    assert [m.id for m in messages] == [first.id, second.id]


async def test_non_participant_cannot_list_messages(db_session: AsyncSession):
    sender = make_caller()
    other = make_caller()
    outsider = make_caller()
    chat = await _create_chat(db_session, sender.id, other.id)
    await _send(db_session, sender, chat.id, "oi")

    with pytest.raises(ChatNotFoundError):
        await _list(db_session, outsider, chat.id)


async def test_send_message_endpoint_persists_and_returns_it(client: AsyncClient):
    user_a_id, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    response = await say(client, chat_id, headers_a, "hello")

    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "hello"
    assert body["chat_id"] == chat_id
    assert body["sender_id"] == user_a_id
    assert body["sender_type"] == "user"


async def test_non_participant_cannot_send_message_via_endpoint(client: AsyncClient):
    headers_a = bearer(caller_token()[1])
    user_b_id, _ = caller_token()
    headers_outsider = bearer(caller_token()[1])
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    response = await say(client, chat_id, headers_outsider, "hello")

    assert response.status_code == 404


async def test_participant_can_fetch_message_backlog_in_order(client: AsyncClient):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, token_b = caller_token()
    headers_b = bearer(token_b)
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    await say(client, chat_id, headers_a, "oi")
    await say(client, chat_id, headers_b, "tudo bem?")

    assert await bodies(client, chat_id, headers_a) == ["oi", "tudo bem?"]


async def test_non_participant_cannot_fetch_backlog_via_endpoint(client: AsyncClient):
    headers_a = bearer(caller_token()[1])
    user_b_id, _ = caller_token()
    headers_outsider = bearer(caller_token()[1])
    chat_id = await open_chat_id(client, headers_a, user_b_id)
    await say(client, chat_id, headers_a, "oi")

    response = await client.get(
        f"/chats/{chat_id}/messages", headers=headers_outsider
    )

    assert response.status_code == 404


async def test_a_message_sent_without_naming_a_visibility_is_visible_to_all(
    client: AsyncClient,
):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    response = await say(client, chat_id, headers_a, "oi")

    assert response.json()["visibility"] == "all"


async def test_a_staff_only_message_is_refused_in_a_staff_chat(client: AsyncClient):
    """Refused rather than quietly downgraded to an ordinary message.

    A silent downgrade is the worse failure: the sender is told their message
    was stored, believes it was restricted, and it was not. There is nobody in
    a Staff Chat the restriction could exclude, so the request describes
    something the service cannot do and says so.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    response = await say(client, chat_id, headers_a, "só a equipe", visibility="staff_only")

    assert response.status_code == 422


async def _client_chat_with_two_staff(client: AsyncClient) -> tuple[str, dict, dict, dict]:
    """A Client Chat holding two of the Company's staff and one end client."""
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    staff_b_id, token_b = caller_token()
    headers_b = bearer(token_b)
    client_c_id, token_c = caller_token(user_kind="client")
    headers_c = bearer(token_c)

    created = await open_chat_of(
        client,
        headers_a,
        (staff_b_id, "staff"),
        (client_c_id, "client"),
        chat_type="client",
        name="Cliente e equipe",
    )
    return created.json()["id"], headers_a, headers_b, headers_c


async def test_a_staff_only_message_reaches_staff_and_not_the_end_client(
    client: AsyncClient,
):
    """The whole of ticket 04 in one thread, read from both sides.

    The Staff-only Message sits *between* two ordinary ones on purpose. An end
    client who saw `["um", "dois"]` with a hole in the ordering would learn one
    exists without reading it, which the rule forbids just as firmly — so the
    assertion is on what they see, not merely on what they do not.
    """
    chat_id, headers_a, headers_b, headers_c = await _client_chat_with_two_staff(client)

    for body, visibility in (("um", "all"), ("segredo", "staff_only"), ("dois", "all")):
        sent = await say(client, chat_id, headers_a, body, visibility=visibility)
        assert sent.status_code == 201

    assert await bodies(client, chat_id, headers_a) == ["um", "segredo", "dois"]
    assert await bodies(client, chat_id, headers_b) == ["um", "segredo", "dois"]
    assert await bodies(client, chat_id, headers_c) == ["um", "dois"]


async def test_an_end_client_cannot_write_a_staff_only_message(client: AsyncClient):
    """Writing is the reading rule backwards, so this needs no rule of its own.

    An end client who could write one would be writing something they could not
    then read — and the Chat would hold a Staff-only Message from outside the
    Company's staff, which is not what the words mean.
    """
    chat_id, _, _, headers_c = await _client_chat_with_two_staff(client)

    response = await say(client, chat_id, headers_c, "e eu?", visibility="staff_only")

    assert response.status_code == 422


async def _last_message_at(client: AsyncClient, chat_id: str, headers: dict) -> str | None:
    response = await client.get("/chats", headers=headers)
    assert response.status_code == 200
    listed = next(chat for chat in response.json() if chat["id"] == chat_id)
    return listed["last_message_at"]


async def test_a_staff_only_message_does_not_stir_the_end_clients_chat_list(
    client: AsyncClient,
):
    """Not learning one exists includes not watching the Chat twitch when one arrives.

    `last_message_at` is both the timestamp shown beside a Chat and the key the
    list is ordered by. Left unfiltered it would tick forward, and reorder the
    list, every time staff said something the end client cannot read — which
    announces the Staff-only Message without quoting it.
    """
    chat_id, headers_a, _, headers_c = await _client_chat_with_two_staff(client)
    await say(client, chat_id, headers_a, "oi")
    before_for_client = await _last_message_at(client, chat_id, headers_c)
    before_for_staff = await _last_message_at(client, chat_id, headers_a)

    await say(client, chat_id, headers_a, "segredo", visibility="staff_only")

    assert await _last_message_at(client, chat_id, headers_c) == before_for_client
    assert await _last_message_at(client, chat_id, headers_a) != before_for_staff
