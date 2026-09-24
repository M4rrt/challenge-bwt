import uuid

from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
import pytest

from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.services.outbox import drain_once
from app.services.realtime import address_for_user, publish
from tests.chats import open_chat
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token
from tests.messages import say


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


async def test_participant_is_notified_over_user_channel_when_chat_is_created(
    client: AsyncClient, db_session: AsyncSession
):
    user_a_id, token_a = caller_token()
    user_b_id, token_b = caller_token()

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/users/me?token={token_b}",
            client=ws_client,
        ) as ws:
            create_response = await open_chat(client, bearer(token_a), user_b_id)
            chat_id = create_response.json()["id"]
            await drain_once(db_session)

            received = await ws.receive_json(timeout=5)

    assert received["id"] == chat_id
    assert set(received["participant_user_ids"]) == {user_a_id, user_b_id}


async def test_participant_is_notified_over_user_channel_when_message_arrives(
    client: AsyncClient, db_session: AsyncSession
):
    user_a_id, token_a = caller_token()
    user_b_id, token_b = caller_token()
    headers_a = bearer(token_a)

    create_response = await open_chat(client, headers_a, user_b_id)
    chat_id = create_response.json()["id"]
    # Creating the Chat enqueued a summary of its own. The drain is FIFO, so
    # without clearing it here the tick below would deliver that one first and
    # this test would assert against the Chat's birth instead of the message.
    await drain_once(db_session)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/users/me?token={token_b}",
            client=ws_client,
        ) as ws:
            send_response = await say(client, chat_id, headers_a, "oi")
            message_created_at = send_response.json()["created_at"]
            await drain_once(db_session)

            received = await ws.receive_json(timeout=5)

    assert received["id"] == chat_id
    assert received["last_message_at"] == message_created_at
    assert received["last_message"]["body"] == "oi"


async def test_the_pushed_summary_never_previews_a_staff_only_message(
    client: AsyncClient, db_session: AsyncSession
):
    """The live chat list carries a message body now, so the rule has to hold here too.

    Ticket 10 gave the summary a `last_message`, and that is a second way a
    Staff-only Message could reach an end client — the first being `GET /chats`.
    The spec's line is "never over the API, never in a count, never as a gap in
    pagination", and a push is none of those three only in the sense that
    nobody had written it down yet.

    What the end client must receive is not silence but the last message they
    *may* read. A summary whose preview went empty while the timestamp stayed
    put would announce the Staff-only Message by the hole it left, which is the
    same failure the list endpoint's own test guards against.
    """
    _, staff_token = caller_token(user_kind="staff")
    end_client_id, end_client_token = caller_token(user_kind="client")
    chat_id = (
        await open_chat(
            client,
            bearer(staff_token),
            end_client_id,
            chat_type="client",
            user_kind="client",
        )
    ).json()["id"]
    await say(client, chat_id, bearer(staff_token), "bom dia")
    # Composition and the visible message both enqueued a summary; the drain is
    # FIFO, so they are cleared here to leave the Staff-only send as the next
    # thing either socket will be told about.
    await drain_once(db_session)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/users/me?token={end_client_token}", client=ws_client
        ) as client_socket:
            async with aconnect_ws(
                f"/websocket/users/me?token={staff_token}", client=ws_client
            ) as staff_socket:
                await say(
                    client, chat_id, bearer(staff_token), "combinado?", visibility="staff_only"
                )
                await drain_once(db_session)

                by_the_client = await client_socket.receive_json(timeout=5)
                by_staff = await staff_socket.receive_json(timeout=5)

    assert by_staff["last_message"]["body"] == "combinado?"
    assert by_the_client["last_message"]["body"] == "bom dia"


async def test_connected_user_receives_message_published_to_their_channel(
    client: AsyncClient,
):
    user_id, token = caller_token()

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/users/me?token={token}",
            client=ws_client,
        ) as ws:
            await publish(
                address_for_user(DEFAULT_COMPANY_ID, uuid.UUID(user_id)).channel,
                '{"hello": "world"}',
            )
            received = await ws.receive_text(timeout=5)

    assert received == '{"hello": "world"}'
