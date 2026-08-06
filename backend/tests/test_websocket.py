from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
import pytest

from app.main import app


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


async def test_participant_receives_message_sent_by_another_participant_over_websocket(
    client: AsyncClient,
):
    user_a_id, headers_a = await _register_and_login(client, "ws-d@example.com")
    user_b_id, headers_b = await _register_and_login(client, "ws-e@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    token_b = headers_b["Authorization"].removeprefix("Bearer ")

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/conversations/{conversation_id}?token={token_b}",
            client=ws_client,
        ) as ws:
            response = await client.post(
                f"/conversations/{conversation_id}/messages",
                json={"body": "oi"},
                headers=headers_a,
            )
            assert response.status_code == 201

            received = await ws.receive_json(timeout=5)

    assert received["body"] == "oi"
    assert received["conversation_id"] == conversation_id
    assert received["sender_id"] == user_a_id
    assert received["sender_type"] == "user"


async def test_non_participant_websocket_connection_is_rejected(client: AsyncClient):
    _, headers_a = await _register_and_login(client, "ws-a@example.com")
    user_b_id, _ = await _register_and_login(client, "ws-b@example.com")
    _, headers_outsider = await _register_and_login(client, "ws-c@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    outsider_token = headers_outsider["Authorization"].removeprefix("Bearer ")

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            async with aconnect_ws(
                f"/websocket/conversations/{conversation_id}?token={outsider_token}",
                client=ws_client,
            ):
                pass

    assert exc_info.value.code == 1008
