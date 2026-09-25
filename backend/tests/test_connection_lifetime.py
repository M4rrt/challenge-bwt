"""A connection's life after the handshake: the warning, the renewal, the deadline.

ADR-0011 made the fifteen-minute token the revocation mechanism, which is only
affordable if an expiry does not cost a reconnect — a reconnect costs a recovery
query and opens a window in which messages are lost. So the service warns, the
client answers over the same socket, and the deadline stays as a backstop.

The tokens here are minted with seconds of life rather than minutes, and the
default warning lead is longer than that, so the warning is already overdue at
the handshake and arrives at once. That is the same code path as a fifteen-minute
token warned about fourteen minutes in; what a test cannot afford is the wait.
"""

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_token import verify_chat_token
from app.core.close_codes import CloseCode
from app.main import app
from app.services import connection
from app.services.outbox import drain_once
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token, mint_chat_token
from tests.chats import acting_for, open_chat_id, open_chat_of
from tests.messages import say
from tests.sockets import closed_with, ignoring_the_close


def expiring_in(seconds: float, user_id: str) -> str:
    """Another token for the same person, with only moments left on it."""
    _, token = caller_token(uuid.UUID(user_id), expires_in=timedelta(seconds=seconds))
    return token


async def test_the_service_warns_the_connection_before_its_credential_expires(
    client: AsyncClient,
):
    user_id, token = caller_token()
    other_id, _ = caller_token()
    chat_id = await open_chat_id(client, bearer(token), other_id)
    expiring = expiring_in(2, user_id)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/chats/{chat_id}?token={expiring}", client=ws_client
        ) as ws:
            warning = await ws.receive_json(timeout=5)

    caller = verify_chat_token(expiring)
    assert caller is not None
    assert warning["type"] == "token.expiring"
    assert datetime.fromisoformat(warning["expires_at"]) == caller.expires_at


async def test_a_connection_whose_renewal_never_arrives_is_closed_as_token_expired(
    client: AsyncClient,
):
    """Not 1008. A client told "unauthenticated" sends its user to a login screen.

    The deadline is the backstop under in-band renewal, and having both is the
    point (ADR-0011): the deadline alone costs a recovery every fifteen minutes,
    and renewal alone leaves a path where a connection whose deadline nobody
    rescheduled lives forever — silently.
    """
    user_id, token = caller_token()
    other_id, _ = caller_token()
    chat_id = await open_chat_id(client, bearer(token), other_id)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with ignoring_the_close():
            async with aconnect_ws(
                f"/websocket/chats/{chat_id}?token={expiring_in(1, user_id)}", client=ws_client
            ) as ws:
                code = await closed_with(ws)

    assert code == CloseCode.TOKEN_EXPIRED
    assert CloseCode.TOKEN_EXPIRED != CloseCode.UNAUTHENTICATED


async def test_a_new_token_over_the_same_connection_carries_it_past_the_old_expiry(
    client: AsyncClient, db_session: AsyncSession
):
    """The whole point: no reconnect, so no recovery query and no window to lose a message in.

    The message sent after the original expiry is what makes this an assertion
    about the connection rather than about a frame: a socket that had been closed
    and silently reopened by nobody would not deliver it.
    """
    user_id, token = caller_token()
    other_id, other_token = caller_token()
    chat_id = await open_chat_id(client, bearer(token), other_id)
    await drain_once(db_session)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/chats/{chat_id}?token={expiring_in(1, user_id)}", client=ws_client
        ) as ws:
            assert (await ws.receive_json(timeout=5))["type"] == "token.expiring"

            await ws.send_json({"type": "token.renew", "token": token})
            confirmation = await ws.receive_json(timeout=5)

            await asyncio.sleep(1.2)
            await say(client, chat_id, bearer(other_token), "ainda aqui")
            await drain_once(db_session)
            arrived = await ws.receive_json(timeout=5)

    renewed = verify_chat_token(token)
    assert renewed is not None
    assert confirmation["type"] == "token.renewed"
    assert datetime.fromisoformat(confirmation["expires_at"]) == renewed.expires_at
    assert arrived["body"] == "ainda aqui"


async def test_a_renewal_from_someone_no_longer_in_the_chat_is_refused_as_access_revoked(
    client: AsyncClient, db_session: AsyncSession
):
    """Renewal is the moment revocation actually happens (ADR-0011).

    The monolith revokes by not issuing the next token, or by issuing it without
    the scope — but losing a *Chat* is not visible in a token at all, so the
    renewal has to re-ask the Chat as well. A token that verifies is not the same
    claim as a Chat that is still yours.

    The removal's own eviction is left undrained on purpose, so that what closes
    this socket is the revalidation and not the eviction. The two are meant to
    overlap: one is immediate and one is the backstop for when the first did not
    arrive.
    """
    user_id, token = caller_token()
    owner_id, owner_token = caller_token()
    chat_id = await open_chat_id(client, bearer(owner_token), user_id)
    await drain_once(db_session)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with ignoring_the_close():
            async with aconnect_ws(
                f"/websocket/chats/{chat_id}?token={expiring_in(2, user_id)}", client=ws_client
            ) as ws:
                assert (await ws.receive_json(timeout=5))["type"] == "token.expiring"

                removed = await client.delete(
                    f"/internal/chats/{chat_id}/participants/{user_id}",
                    headers=acting_for(owner_id, str(DEFAULT_COMPANY_ID)),
                )
                assert removed.status_code == 200

                await ws.send_json({"type": "token.renew", "token": token})
                code = await closed_with(ws)

    assert code == CloseCode.ACCESS_REVOKED


async def test_a_renewal_that_demotes_the_caller_takes_them_off_the_staff_address(
    client: AsyncClient, db_session: AsyncSession
):
    """The gap ticket 07 recorded against itself, closed.

    The staff address was joined at the handshake and the handshake was never
    revisited, so a Participant whose kind changed from staff to client kept
    receiving Staff-only Messages for the rest of that connection's life. They
    are still in the Chat — so this is not a revocation — they are simply
    entitled to one address fewer.

    The ordinary message after the Staff-only one is what makes the silence mean
    something: a socket that had merely died would produce the same evidence.
    """
    staff_id, staff_token = caller_token()
    buyer_id, _ = caller_token(user_kind="client")
    created = await open_chat_of(
        client, bearer(staff_token), (buyer_id, "client"), chat_type="client"
    )
    chat_id = created.json()["id"]
    await drain_once(db_session)

    demoted = mint_chat_token(user_id=uuid.UUID(staff_id), user_kind="client")

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/chats/{chat_id}?token={expiring_in(2, staff_id)}", client=ws_client
        ) as ws:
            assert (await ws.receive_json(timeout=5))["type"] == "token.expiring"

            await ws.send_json({"type": "token.renew", "token": demoted})
            assert (await ws.receive_json(timeout=5))["type"] == "token.renewed"

            await say(client, chat_id, bearer(staff_token), "segredo", visibility="staff_only")
            await say(client, chat_id, bearer(staff_token), "publico")
            await drain_once(db_session)

            arrived = await ws.receive_json(timeout=5)

    assert arrived["body"] == "publico"


async def test_an_open_connection_revalidates_on_its_own_without_being_renewed(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """The backstop for everything nobody announces: a deactivation, a lost supervision scope.

    Renewal covers a permission that a token can express and a Chat the caller
    was removed from *at the moment they renew*. What it does not cover is the
    fourteen minutes before that, on a connection whose eviction never arrived —
    a drain that had stopped, an instance that missed the frame. So an open
    connection re-asks on its own, and the window is one interval rather than one
    token lifetime.

    The interval is shortened here because the real one is a minute. The token is
    a full-length one so that nothing in this test can be explained by an expiry.
    """
    monkeypatch.setattr(connection, "REVALIDATION_INTERVAL", timedelta(seconds=0.2))

    user_id, token = caller_token()
    owner_id, owner_token = caller_token()
    chat_id = await open_chat_id(client, bearer(owner_token), user_id)
    await drain_once(db_session)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with ignoring_the_close():
            async with aconnect_ws(
                f"/websocket/chats/{chat_id}?token={token}", client=ws_client
            ) as ws:
                removed = await client.delete(
                    f"/internal/chats/{chat_id}/participants/{user_id}",
                    headers=acting_for(owner_id, str(DEFAULT_COMPANY_ID)),
                )
                assert removed.status_code == 200

                code = await closed_with(ws)

    assert code == CloseCode.ACCESS_REVOKED
