import hashlib
import hmac
import json
import uuid

from httpx import AsyncClient
from httpx_ws.transport import ASGIWebSocketTransport
from httpx_ws import aconnect_ws

from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.services.outbox import drain_once
from tests.chats import open_chat_id
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token


def _sign(body: bytes) -> str:
    return hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()


async def test_valid_signature_persists_external_message(client: AsyncClient):
    _, _token = caller_token()
    headers_a = bearer(_token)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    body = json.dumps(
        {
            "company_id": str(DEFAULT_COMPANY_ID),
            "chat_id": chat_id,
            "body": "shipped",
            "source_label": "Shipping Bot",
        }
    ).encode()

    response = await client.post(
        "/webhook/messages",
        content=body,
        headers={"X-Signature": _sign(body), "Content-Type": "application/json"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["chat_id"] == chat_id
    assert payload["body"] == "shipped"
    assert payload["sender_id"] is None
    assert payload["sender_type"] == "external"
    assert payload["source_label"] == "Shipping Bot"


async def test_missing_signature_is_rejected(client: AsyncClient):
    _, _token = caller_token()
    headers_a = bearer(_token)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    body = json.dumps({
        "company_id": str(DEFAULT_COMPANY_ID),
        "chat_id": chat_id,
        "body": "no signature",
    }).encode()

    response = await client.post(
        "/webhook/messages",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401


async def test_tampered_body_is_rejected(client: AsyncClient):
    _, _token = caller_token()
    headers_a = bearer(_token)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    original_body = json.dumps({
        "company_id": str(DEFAULT_COMPANY_ID),
        "chat_id": chat_id,
        "body": "original",
    }).encode()
    signature = _sign(original_body)
    tampered_body = json.dumps({
        "company_id": str(DEFAULT_COMPANY_ID),
        "chat_id": chat_id,
        "body": "tampered",
    }).encode()

    response = await client.post(
        "/webhook/messages",
        content=tampered_body,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 401


async def test_unknown_chat_id_is_rejected(client: AsyncClient):
    unknown_chat_id = str(uuid.uuid4())
    body = json.dumps(
        {
            "company_id": str(DEFAULT_COMPANY_ID),
            "chat_id": unknown_chat_id,
            "body": "nobody's home",
        }
    ).encode()

    response = await client.post(
        "/webhook/messages",
        content=body,
        headers={"X-Signature": _sign(body), "Content-Type": "application/json"},
    )

    assert response.status_code == 404


async def test_webhook_message_delivered_live_to_connected_participant(
    client: AsyncClient, db_session: AsyncSession
):
    user_a_id, _token = caller_token()
    headers_a = bearer(_token)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    token_a = headers_a["Authorization"].removeprefix("Bearer ")

    body = json.dumps(
        {
            "company_id": str(DEFAULT_COMPANY_ID),
            "chat_id": chat_id,
            "body": "shipped",
            "source_label": "Shipping Bot",
        }
    ).encode()

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/chats/{chat_id}?token={token_a}",
            client=ws_client,
        ) as ws:
            response = await client.post(
                "/webhook/messages",
                content=body,
                headers={"X-Signature": _sign(body), "Content-Type": "application/json"},
            )
            assert response.status_code == 201
            await drain_once(db_session)

            received = await ws.receive_json(timeout=5)

    assert received["body"] == "shipped"
    assert received["chat_id"] == chat_id
    assert received["sender_id"] is None
    assert received["sender_type"] == "external"
    assert received["source_label"] == "Shipping Bot"


async def test_webhook_message_not_delivered_to_other_chat(
    client: AsyncClient, db_session: AsyncSession
):
    user_a_id, _token = caller_token()
    headers_a = bearer(_token)
    user_b_id, _ = caller_token()
    target_chat_id = await open_chat_id(client, headers_a, user_b_id)

    user_c_id, _token = caller_token()
    headers_c = bearer(_token)
    user_d_id, _ = caller_token()
    other_chat_id = await open_chat_id(client, headers_c, user_d_id)

    token_c = headers_c["Authorization"].removeprefix("Bearer ")

    body = json.dumps({
        "company_id": str(DEFAULT_COMPANY_ID),
        "chat_id": target_chat_id,
        "body": "shipped",
    }).encode()

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/chats/{other_chat_id}?token={token_c}",
            client=ws_client,
        ) as ws:
            response = await client.post(
                "/webhook/messages",
                content=body,
                headers={"X-Signature": _sign(body), "Content-Type": "application/json"},
            )
            assert response.status_code == 201

            # confirm the other chat's own traffic still works, proving the
            # earlier lack of a message isn't just a dead/slow socket
            own_body = json.dumps(
                {
                    "company_id": str(DEFAULT_COMPANY_ID),
                    "chat_id": other_chat_id,
                    "body": "own message",
                }
            ).encode()
            own_response = await client.post(
                "/webhook/messages",
                content=own_body,
                headers={"X-Signature": _sign(own_body), "Content-Type": "application/json"},
            )
            assert own_response.status_code == 201
            await drain_once(db_session)

            received = await ws.receive_json(timeout=5)

    assert received["body"] == "own message"
    assert received["chat_id"] == other_chat_id


async def test_invalid_signature_is_rejected(client: AsyncClient):
    _, _token = caller_token()
    headers_a = bearer(_token)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    body = json.dumps({
        "company_id": str(DEFAULT_COMPANY_ID),
        "chat_id": chat_id,
        "body": "bad signature",
    }).encode()

    response = await client.post(
        "/webhook/messages",
        content=body,
        headers={"X-Signature": "0" * 64, "Content-Type": "application/json"},
    )

    assert response.status_code == 401
