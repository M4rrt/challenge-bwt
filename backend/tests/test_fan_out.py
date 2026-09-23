"""The three addresses, seen from the sockets listening on them.

Ticket 04 made a Staff-only Message invisible to an end client in the API. This
is the same rule at the transport, and it is not enforced by a second check:
the end client's socket never joined the staff address, so there is nothing to
filter and nothing for a future emitter to forget.
"""

from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.services.outbox import drain_once
from tests.chat_tokens import bearer, caller_token
from tests.chats import open_chat_of


async def test_a_staff_only_message_reaches_the_staff_socket_and_not_the_end_clients(
    client: AsyncClient, db_session: AsyncSession
):
    """Both sockets are on the same Chat; only one of them is on the staff address.

    The ordinary message after the Staff-only one is what makes the end client's
    silence mean something. Without it, a socket that had simply died would
    produce the same evidence — which is the shape of assertion `test_webhook.py`
    already uses for the same reason.
    """
    staff_a_id, token_a = caller_token()
    headers_a = bearer(token_a)
    staff_b_id, token_b = caller_token()
    client_c_id, token_c = caller_token(user_kind="client")

    created = await open_chat_of(
        client,
        headers_a,
        (staff_b_id, "staff"),
        (client_c_id, "client"),
        chat_type="client",
        name="Cliente e equipe",
    )
    chat_id = created.json()["id"]
    await drain_once(db_session)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with (
            aconnect_ws(f"/websocket/chats/{chat_id}?token={token_b}", client=ws_client) as staff,
            aconnect_ws(f"/websocket/chats/{chat_id}?token={token_c}", client=ws_client) as buyer,
        ):
            for body, visibility in (("um", "all"), ("segredo", "staff_only"), ("dois", "all")):
                await client.post(
                    f"/chats/{chat_id}/messages",
                    json={"body": body, "visibility": visibility},
                    headers=headers_a,
                )
            await drain_once(db_session)

            staff_saw = [(await staff.receive_json(timeout=5))["body"] for _ in range(3)]
            buyer_saw = [(await buyer.receive_json(timeout=5))["body"] for _ in range(2)]

    assert staff_saw == ["um", "segredo", "dois"]
    assert buyer_saw == ["um", "dois"]
