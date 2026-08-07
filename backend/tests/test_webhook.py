import hashlib
import hmac
import json
import uuid

from httpx import AsyncClient
from httpx_ws.transport import ASGIWebSocketTransport
from httpx_ws import aconnect_ws

from app.core.config import settings
from app.main import app


def _sign(body: bytes) -> str:
    return hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()


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


async def test_valid_signature_persists_external_message(client: AsyncClient):
    _, headers_a = await _register_and_login(client, "wh-a@example.com")
    user_b_id, _ = await _register_and_login(client, "wh-b@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    body = json.dumps(
        {"conversation_id": conversation_id, "body": "shipped", "source_label": "Shipping Bot"}
    ).encode()

    response = await client.post(
        "/webhook/messages",
        content=body,
        headers={"X-Signature": _sign(body), "Content-Type": "application/json"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["conversation_id"] == conversation_id
    assert payload["body"] == "shipped"
    assert payload["sender_id"] is None
    assert payload["sender_type"] == "external"
    assert payload["source_label"] == "Shipping Bot"


async def test_missing_signature_is_rejected(client: AsyncClient):
    _, headers_a = await _register_and_login(client, "wh-c@example.com")
    user_b_id, _ = await _register_and_login(client, "wh-d@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    body = json.dumps({"conversation_id": conversation_id, "body": "no signature"}).encode()

    response = await client.post(
        "/webhook/messages",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401


async def test_tampered_body_is_rejected(client: AsyncClient):
    _, headers_a = await _register_and_login(client, "wh-g@example.com")
    user_b_id, _ = await _register_and_login(client, "wh-h@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    original_body = json.dumps({"conversation_id": conversation_id, "body": "original"}).encode()
    signature = _sign(original_body)
    tampered_body = json.dumps({"conversation_id": conversation_id, "body": "tampered"}).encode()

    response = await client.post(
        "/webhook/messages",
        content=tampered_body,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 401


async def test_unknown_conversation_id_is_rejected(client: AsyncClient):
    unknown_conversation_id = str(uuid.uuid4())
    body = json.dumps(
        {"conversation_id": unknown_conversation_id, "body": "nobody's home"}
    ).encode()

    response = await client.post(
        "/webhook/messages",
        content=body,
        headers={"X-Signature": _sign(body), "Content-Type": "application/json"},
    )

    assert response.status_code == 404


async def test_webhook_message_delivered_live_to_connected_participant(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "wh-i@example.com")
    user_b_id, _ = await _register_and_login(client, "wh-j@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    token_a = headers_a["Authorization"].removeprefix("Bearer ")

    body = json.dumps(
        {"conversation_id": conversation_id, "body": "shipped", "source_label": "Shipping Bot"}
    ).encode()

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/conversations/{conversation_id}?token={token_a}",
            client=ws_client,
        ) as ws:
            response = await client.post(
                "/webhook/messages",
                content=body,
                headers={"X-Signature": _sign(body), "Content-Type": "application/json"},
            )
            assert response.status_code == 201

            received = await ws.receive_json(timeout=5)

    assert received["body"] == "shipped"
    assert received["conversation_id"] == conversation_id
    assert received["sender_id"] is None
    assert received["sender_type"] == "external"
    assert received["source_label"] == "Shipping Bot"


async def test_webhook_message_not_delivered_to_other_conversation(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "wh-k@example.com")
    user_b_id, _ = await _register_and_login(client, "wh-l@example.com")
    target_conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    user_c_id, headers_c = await _register_and_login(client, "wh-m@example.com")
    user_d_id, _ = await _register_and_login(client, "wh-n@example.com")
    other_conversation_id = await _create_conversation_via_api(client, headers_c, [user_d_id])

    token_c = headers_c["Authorization"].removeprefix("Bearer ")

    body = json.dumps({"conversation_id": target_conversation_id, "body": "shipped"}).encode()

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/conversations/{other_conversation_id}?token={token_c}",
            client=ws_client,
        ) as ws:
            response = await client.post(
                "/webhook/messages",
                content=body,
                headers={"X-Signature": _sign(body), "Content-Type": "application/json"},
            )
            assert response.status_code == 201

            # confirm the other conversation's own traffic still works, proving the
            # earlier lack of a message isn't just a dead/slow socket
            own_body = json.dumps(
                {"conversation_id": other_conversation_id, "body": "own message"}
            ).encode()
            own_response = await client.post(
                "/webhook/messages",
                content=own_body,
                headers={"X-Signature": _sign(own_body), "Content-Type": "application/json"},
            )
            assert own_response.status_code == 201

            received = await ws.receive_json(timeout=5)

    assert received["body"] == "own message"
    assert received["conversation_id"] == other_conversation_id


async def test_invalid_signature_is_rejected(client: AsyncClient):
    _, headers_a = await _register_and_login(client, "wh-e@example.com")
    user_b_id, _ = await _register_and_login(client, "wh-f@example.com")
    conversation_id = await _create_conversation_via_api(client, headers_a, [user_b_id])

    body = json.dumps({"conversation_id": conversation_id, "body": "bad signature"}).encode()

    response = await client.post(
        "/webhook/messages",
        content=body,
        headers={"X-Signature": "0" * 64, "Content-Type": "application/json"},
    )

    assert response.status_code == 401
