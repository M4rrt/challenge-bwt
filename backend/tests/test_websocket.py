from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
import pytest

from app.main import app
from tests.chat_tokens import bearer, caller_token


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
    user_a_id, _token = caller_token()
    headers_a = bearer(_token)
    user_b_id, _token = caller_token()
    headers_b = bearer(_token)
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
    _, _token = caller_token()
    headers_a = bearer(_token)
    user_b_id, _ = caller_token()
    _, _token = caller_token()
    headers_outsider = bearer(_token)
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
