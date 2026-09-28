"""Typing: announced to the Chat, unstored, and gone on its own.

Ticket 12. There is no `typing.stop` and no Redis key behind this one at all —
each announcement carries `expires_at` a few seconds out, and a client that
stops hearing it repeated lets its own indicator lapse at that deadline rather
than waiting for a message that says so.
"""

import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.main import app
from tests.chat_tokens import bearer, caller_token
from tests.chats import open_chat_id, open_chat_of
from tests.sockets import receive_until


async def test_typing_is_announced_to_the_other_participant_of_the_chat(client: AsyncClient):
    user_a_id, token_a = caller_token()
    user_b_id, token_b = caller_token()
    chat_id = await open_chat_id(client, bearer(token_a), user_b_id)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with (
            aconnect_ws(f"/websocket/chats/{chat_id}?token={token_a}", client=ws_client) as typer,
            aconnect_ws(f"/websocket/chats/{chat_id}?token={token_b}", client=ws_client) as other,
        ):
            await typer.send_json({"type": "typing"})
            announced = await receive_until(other, lambda frame: frame["type"] == "typing")

    assert announced["chat_id"] == chat_id
    assert announced["user_id"] == user_a_id
    assert datetime.fromisoformat(announced["expires_at"]) > datetime.now(timezone.utc)


async def test_typing_never_crosses_a_company(client: AsyncClient):
    """A Client Chat is beside the point here — there is no staff-only typing.

    Typing is addressed to the plain Chat channel, which already carries the
    Company in its key, the same structural guarantee every other address in
    `realtime.py` relies on — exercised for this one too rather than assumed.
    """
    staff_id, staff_token = caller_token()
    buyer_id, buyer_token = caller_token(user_kind="client")
    created = await open_chat_of(
        client,
        bearer(staff_token),
        (buyer_id, "client"),
        chat_type="client",
    )
    chat_id = created.json()["id"]

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with (
            aconnect_ws(
                f"/websocket/chats/{chat_id}?token={staff_token}", client=ws_client
            ) as staff,
            aconnect_ws(
                f"/websocket/chats/{chat_id}?token={buyer_token}", client=ws_client
            ) as buyer,
        ):
            await staff.send_json({"type": "typing"})
            seen_by_buyer = await receive_until(buyer, lambda frame: frame["type"] == "typing")

    assert seen_by_buyer["user_id"] == staff_id


async def test_typing_on_the_users_own_socket_is_ignored(client: AsyncClient):
    """The own socket names no Chat, so there is nowhere to announce it to.

    Proven by the connection staying alive and answering the next, known frame
    — a `typing` that crashed the handler would take the renewal down with it
    rather than merely producing no announcement.
    """
    user_id, token = caller_token()

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(f"/websocket/users/me?token={token}", client=ws_client) as ws:
            await ws.send_json({"type": "typing"})

            _, renewal = caller_token(user_id=uuid.UUID(user_id))
            await ws.send_json({"type": "token.renew", "token": renewal})
            confirmation = await ws.receive_json(timeout=5)

    assert confirmation["type"] == "token.renewed"
