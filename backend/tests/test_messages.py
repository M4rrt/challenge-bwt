import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationParticipant
from app.models.user import User
from app.schemas.message import MessageCreate
from app.services.message import ConversationNotFoundError, list_messages, send_message


async def _create_user(db: AsyncSession, email: str) -> User:
    user = User(email=email, username=email.split("@")[0], hashed_password="hashed")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_conversation(db: AsyncSession, *user_ids: uuid.UUID) -> Conversation:
    conversation = Conversation(name=None)
    conversation.participants = [ConversationParticipant(user_id=uid) for uid in user_ids]
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def test_participant_can_send_message(db_session: AsyncSession):
    user_a = await _create_user(db_session, "msg-a@example.com")
    user_b = await _create_user(db_session, "msg-b@example.com")
    conversation = await _create_conversation(db_session, user_a.id, user_b.id)

    message = await send_message(db_session, user_a, conversation.id, MessageCreate(body="oi"))

    assert message.body == "oi"
    assert message.conversation_id == conversation.id
    assert message.sender_id == user_a.id
    assert message.sender_type == "user"


async def test_non_participant_cannot_send_message(db_session: AsyncSession):
    user_a = await _create_user(db_session, "msg-c@example.com")
    user_b = await _create_user(db_session, "msg-d@example.com")
    outsider = await _create_user(db_session, "msg-e@example.com")
    conversation = await _create_conversation(db_session, user_a.id, user_b.id)

    with pytest.raises(ConversationNotFoundError):
        await send_message(db_session, outsider, conversation.id, MessageCreate(body="oi"))


async def test_participant_can_list_messages_in_order(db_session: AsyncSession):
    user_a = await _create_user(db_session, "msg-f@example.com")
    user_b = await _create_user(db_session, "msg-g@example.com")
    conversation = await _create_conversation(db_session, user_a.id, user_b.id)

    first = await send_message(db_session, user_a, conversation.id, MessageCreate(body="first"))
    second = await send_message(db_session, user_b, conversation.id, MessageCreate(body="second"))

    messages = await list_messages(db_session, user_a, conversation.id)

    assert [m.id for m in messages] == [first.id, second.id]


async def test_non_participant_cannot_list_messages(db_session: AsyncSession):
    user_a = await _create_user(db_session, "msg-h@example.com")
    user_b = await _create_user(db_session, "msg-i@example.com")
    outsider = await _create_user(db_session, "msg-j@example.com")
    conversation = await _create_conversation(db_session, user_a.id, user_b.id)
    await send_message(db_session, user_a, conversation.id, MessageCreate(body="oi"))

    with pytest.raises(ConversationNotFoundError):
        await list_messages(db_session, outsider, conversation.id)


async def _register_and_login(client: AsyncClient, email: str) -> tuple[str, dict[str, str]]:
    username = email.split("@")[0]
    register_response = await client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": "Senha-Forte-123"},
    )
    user_id = register_response.json()["id"]

    login_response = await client.post(
        "/auth/login", json={"email": email, "password": "Senha-Forte-123"}
    )
    token = login_response.json()["access_token"]

    return user_id, {"Authorization": f"Bearer {token}"}


async def _create_conversation_via_api(
    client: AsyncClient, headers: dict[str, str], participant_ids: list[str]
) -> str:
    response = await client.post(
        "/conversations",
        json={"participant_user_ids": participant_ids},
        headers=headers,
    )
    return response.json()["id"]


async def test_send_message_endpoint_persists_and_returns_it(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "http-a@example.com")
    user_b_id, _ = await _register_and_login(client, "http-b@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"body": "hello"},
        headers=headers_a,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "hello"
    assert body["conversation_id"] == conversation_id
    assert body["sender_id"] == user_a_id
    assert body["sender_type"] == "user"


async def test_non_participant_cannot_send_message_via_endpoint(client: AsyncClient):
    _, headers_a = await _register_and_login(client, "http-c@example.com")
    user_b_id, _ = await _register_and_login(client, "http-d@example.com")
    _, headers_outsider = await _register_and_login(client, "http-e@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"body": "hello"},
        headers=headers_outsider,
    )

    assert response.status_code == 404


async def test_participant_can_fetch_message_backlog_in_order(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "http-f@example.com")
    user_b_id, headers_b = await _register_and_login(client, "http-g@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    await client.post(
        f"/conversations/{conversation_id}/messages", json={"body": "oi"}, headers=headers_a
    )
    await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"body": "tudo bem?"},
        headers=headers_b,
    )

    response = await client.get(f"/conversations/{conversation_id}/messages", headers=headers_a)

    assert response.status_code == 200
    bodies = [m["body"] for m in response.json()]
    assert bodies == ["oi", "tudo bem?"]


async def test_non_participant_cannot_fetch_backlog_via_endpoint(client: AsyncClient):
    _, headers_a = await _register_and_login(client, "http-h@example.com")
    user_b_id, _ = await _register_and_login(client, "http-i@example.com")
    _, headers_outsider = await _register_and_login(client, "http-j@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])
    await client.post(
        f"/conversations/{conversation_id}/messages", json={"body": "oi"}, headers=headers_a
    )

    response = await client.get(
        f"/conversations/{conversation_id}/messages", headers=headers_outsider
    )

    assert response.status_code == 404
