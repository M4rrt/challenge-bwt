import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationParticipant
from app.schemas.message import MessageCreate
from app.services.message import ConversationNotFoundError, list_messages, send_message
from tests.chat_tokens import bearer, caller_token, make_caller


async def _create_conversation(db: AsyncSession, *user_ids: uuid.UUID) -> Conversation:
    conversation = Conversation(name=None)
    conversation.participants = [ConversationParticipant(user_id=uid) for uid in user_ids]
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def test_participant_can_send_message(db_session: AsyncSession):
    sender = make_caller()
    other = make_caller()
    conversation = await _create_conversation(db_session, sender.id, other.id)

    message = await send_message(db_session, sender, conversation.id, MessageCreate(body="oi"))

    assert message.body == "oi"
    assert message.conversation_id == conversation.id
    assert message.sender_id == sender.id
    assert message.sender_type == "user"


async def test_non_participant_cannot_send_message(db_session: AsyncSession):
    sender = make_caller()
    other = make_caller()
    outsider = make_caller()
    conversation = await _create_conversation(db_session, sender.id, other.id)

    with pytest.raises(ConversationNotFoundError):
        await send_message(db_session, outsider, conversation.id, MessageCreate(body="oi"))


async def test_participant_can_list_messages_in_order(db_session: AsyncSession):
    sender = make_caller()
    other = make_caller()
    conversation = await _create_conversation(db_session, sender.id, other.id)

    first = await send_message(db_session, sender, conversation.id, MessageCreate(body="first"))
    second = await send_message(db_session, other, conversation.id, MessageCreate(body="second"))

    messages = await list_messages(db_session, sender, conversation.id)

    assert [m.id for m in messages] == [first.id, second.id]


async def test_non_participant_cannot_list_messages(db_session: AsyncSession):
    sender = make_caller()
    other = make_caller()
    outsider = make_caller()
    conversation = await _create_conversation(db_session, sender.id, other.id)
    await send_message(db_session, sender, conversation.id, MessageCreate(body="oi"))

    with pytest.raises(ConversationNotFoundError):
        await list_messages(db_session, outsider, conversation.id)


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
    user_a_id, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
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
    headers_a = bearer(caller_token()[1])
    user_b_id, _ = caller_token()
    headers_outsider = bearer(caller_token()[1])
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"body": "hello"},
        headers=headers_outsider,
    )

    assert response.status_code == 404


async def test_participant_can_fetch_message_backlog_in_order(client: AsyncClient):
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, token_b = caller_token()
    headers_b = bearer(token_b)
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
    headers_a = bearer(caller_token()[1])
    user_b_id, _ = caller_token()
    headers_outsider = bearer(caller_token()[1])
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])
    await client.post(
        f"/conversations/{conversation_id}/messages", json={"body": "oi"}, headers=headers_a
    )

    response = await client.get(
        f"/conversations/{conversation_id}/messages", headers=headers_outsider
    )

    assert response.status_code == 404
