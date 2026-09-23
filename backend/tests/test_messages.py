import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import Caller
from app.core.company_scope import CompanyScope
from app.models.chat import Chat, ChatType, Participant, ParticipantRole
from app.schemas.message import MessageCreate
from app.services.message import ChatNotFoundError, list_messages, send_message
from tests.chats import open_chat_id
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token, make_caller


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
    return await send_message(db, scope, caller, chat_id, MessageCreate(body=body))


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

    response = await client.post(
        f"/chats/{chat_id}/messages",
        json={"body": "hello"},
        headers=headers_a,
    )

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

    response = await client.post(
        f"/chats/{chat_id}/messages",
        json={"body": "hello"},
        headers=headers_outsider,
    )

    assert response.status_code == 404


async def test_participant_can_fetch_message_backlog_in_order(client: AsyncClient):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, token_b = caller_token()
    headers_b = bearer(token_b)
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    await client.post(
        f"/chats/{chat_id}/messages", json={"body": "oi"}, headers=headers_a
    )
    await client.post(
        f"/chats/{chat_id}/messages",
        json={"body": "tudo bem?"},
        headers=headers_b,
    )

    response = await client.get(f"/chats/{chat_id}/messages", headers=headers_a)

    assert response.status_code == 200
    bodies = [m["body"] for m in response.json()]
    assert bodies == ["oi", "tudo bem?"]


async def test_non_participant_cannot_fetch_backlog_via_endpoint(client: AsyncClient):
    headers_a = bearer(caller_token()[1])
    user_b_id, _ = caller_token()
    headers_outsider = bearer(caller_token()[1])
    chat_id = await open_chat_id(client, headers_a, user_b_id)
    await client.post(
        f"/chats/{chat_id}/messages", json={"body": "oi"}, headers=headers_a
    )

    response = await client.get(
        f"/chats/{chat_id}/messages", headers=headers_outsider
    )

    assert response.status_code == 404
