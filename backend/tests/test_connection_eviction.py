"""Losing access closes exactly the affected connections, and no others.

Authorising only at connect time means removing a Participant announces it to
the Chat and evicts nobody: until they reconnect, that person keeps receiving
messages (ADR-0011). So the connections are indexed by Chat *and* by user — by
user because the token stays valid for everything else, and by Chat because
losing one Chat is not losing chat.

The eviction travels the same Redis path as a delivery, because the connection
being closed is almost never on the instance that handled the removal. It is not
a delivery, though: it names sockets rather than an audience, so it goes on a
channel of its own rather than being sniffed out of a payload.
"""

from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.close_codes import CloseCode
from app.main import app
from app.services.outbox import drain_once
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token
from tests.chats import acting_for, open_chat, open_chat_id
from tests.messages import say
from tests.sockets import closed_with, ignoring_the_close


async def test_removing_a_participant_closes_their_connections_in_that_chat_alone(
    client: AsyncClient, db_session: AsyncSession
):
    """Three sockets, one user, one removal. Exactly one of them goes.

    The other two are proven alive by what they go on to receive rather than by
    the absence of a close: a socket that had quietly died would also fail to
    report one.
    """
    user_id, token = caller_token()
    owner_id, owner_token = caller_token()
    third_id, _ = caller_token()
    headers = bearer(owner_token)

    losing = await open_chat_id(client, headers, user_id)
    keeping = (await open_chat(client, headers, user_id, third_id, name="Equipe")).json()["id"]
    await drain_once(db_session)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with ignoring_the_close():
            async with (
                aconnect_ws(
                    f"/websocket/chats/{losing}?token={token}", client=ws_client
                ) as evicted,
                aconnect_ws(
                    f"/websocket/chats/{keeping}?token={token}", client=ws_client
                ) as elsewhere,
                aconnect_ws(f"/websocket/users/me?token={token}", client=ws_client) as own,
            ):
                removed = await client.delete(
                    f"/internal/chats/{losing}/participants/{user_id}",
                    headers=acting_for(owner_id, str(DEFAULT_COMPANY_ID)),
                )
                assert removed.status_code == 200
                await drain_once(db_session)

                code = await closed_with(evicted)

                await say(client, keeping, headers, "ainda aqui")
                await drain_once(db_session)
                still_delivering = await elsewhere.receive_json(timeout=5)
                still_summarising = await own.receive_json(timeout=5)

    assert code == CloseCode.ACCESS_REVOKED
    assert still_delivering["body"] == "ainda aqui"
    assert still_summarising["id"] == keeping
