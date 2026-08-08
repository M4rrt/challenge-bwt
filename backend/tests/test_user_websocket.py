import uuid

from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
import pytest

from app.main import app
from app.services.realtime import publish_to_user


async def _register_and_login(client: AsyncClient, email: str) -> tuple[str, str]:
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

    return user_id, token


async def test_invalid_token_rejects_user_websocket_connection(client: AsyncClient):
    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            async with aconnect_ws(
                "/websocket/users/me?token=not-a-real-token",
                client=ws_client,
            ):
                pass

    assert exc_info.value.code == 1008


async def test_participant_is_notified_over_user_channel_when_conversation_is_created(
    client: AsyncClient,
):
    user_a_id, token_a = await _register_and_login(client, "user-ws-b@example.com")
    user_b_id, token_b = await _register_and_login(client, "user-ws-c@example.com")

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/users/me?token={token_b}",
            client=ws_client,
        ) as ws:
            create_response = await client.post(
                "/conversations",
                json={"participant_user_ids": [user_b_id]},
                headers={"Authorization": f"Bearer {token_a}"},
            )
            conversation_id = create_response.json()["id"]

            received = await ws.receive_json(timeout=5)

    assert received["id"] == conversation_id
    assert set(received["participant_user_ids"]) == {user_a_id, user_b_id}


async def test_participant_is_notified_over_user_channel_when_message_arrives(
    client: AsyncClient,
):
    user_a_id, token_a = await _register_and_login(client, "user-ws-d@example.com")
    user_b_id, token_b = await _register_and_login(client, "user-ws-e@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    create_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )
    conversation_id = create_response.json()["id"]

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/users/me?token={token_b}",
            client=ws_client,
        ) as ws:
            send_response = await client.post(
                f"/conversations/{conversation_id}/messages",
                json={"body": "oi"},
                headers=headers_a,
            )
            message_created_at = send_response.json()["created_at"]

            received = await ws.receive_json(timeout=5)

    assert received["id"] == conversation_id
    assert received["last_message_at"] == message_created_at


async def test_connected_user_receives_message_published_to_their_channel(
    client: AsyncClient,
):
    user_id, token = await _register_and_login(client, "user-ws-a@example.com")

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/users/me?token={token}",
            client=ws_client,
        ) as ws:
            await publish_to_user(uuid.UUID(user_id), '{"hello": "world"}')
            received = await ws.receive_text(timeout=5)

    assert received == '{"hello": "world"}'
