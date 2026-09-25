"""The exception path: a credential the service stops believing before it expires.

ADR-0011 made the fifteen-minute token the revocation mechanism, and that is the
normal path — the monolith revokes by not issuing the next one. Fifteen minutes
is too long for a dismissal or a ban, so an event from the monolith can put a
user or a single token on a short-lived denylist and close what they hold.

Entries expire alongside the token they block, which is what keeps this from
becoming the distributed revocation list the ADR refused: nothing here has to be
cleaned up, and nothing here is consulted about a token that has run out anyway.
"""

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.close_codes import CloseCode
from app.core.config import settings
from app.main import app
from app.services.denylist import redis_client, token_key, user_key
from app.services.outbox import drain_once
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token
from tests.chats import open_chat, open_chat_id, service_credential
from tests.sockets import closed_with, ignoring_the_close


@pytest.fixture(autouse=True)
async def forget_what_was_denied():
    """Redis is not rolled back with the transaction, so the keys are swept by hand.

    Every test here mints its own identifiers, so nothing collides; what this
    stops is a developer's Redis quietly holding a quarter-hour of denials from
    a test run.
    """
    yield
    keys = [key async for key in redis_client.scan_iter(match="denylist:*")]
    if keys:
        await redis_client.delete(*keys)


async def revoke(client: AsyncClient, **named: str) -> None:
    response = await client.post(
        "/internal/revocations",
        json={"company_id": str(DEFAULT_COMPANY_ID)} | named,
        headers=service_credential(),
    )
    assert response.status_code == 204, response.text


async def test_a_revocation_closes_every_connection_that_user_holds(
    client: AsyncClient, db_session: AsyncSession
):
    """A ban is not the loss of one Chat, so it is not indexed by one.

    The same eviction that a removal writes, addressed to the person rather than
    to the person-in-a-Chat.
    """
    user_id, token = caller_token()
    owner_id, owner_token = caller_token()
    third_id, _ = caller_token()
    headers = bearer(owner_token)

    one = await open_chat_id(client, headers, user_id)
    two = (await open_chat(client, headers, user_id, third_id, name="Equipe")).json()["id"]
    await drain_once(db_session)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with ignoring_the_close():
            async with (
                aconnect_ws(f"/websocket/chats/{one}?token={token}", client=ws_client) as first,
                aconnect_ws(f"/websocket/chats/{two}?token={token}", client=ws_client) as second,
                aconnect_ws(f"/websocket/users/me?token={token}", client=ws_client) as own,
            ):
                await revoke(client, user_id=user_id)
                await drain_once(db_session)

                codes = [await closed_with(socket) for socket in (first, second, own)]

    assert codes == [CloseCode.ACCESS_REVOKED] * 3


async def test_a_denied_user_cannot_open_a_connection_with_a_token_that_still_verifies(
    client: AsyncClient,
):
    """Otherwise the eviction is a closed door somebody walks straight back through."""
    user_id, token = caller_token()
    _, owner_token = caller_token()
    chat_id = await open_chat_id(client, bearer(owner_token), user_id)

    await revoke(client, user_id=user_id)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with pytest.raises(WebSocketDisconnect) as refused:
            async with aconnect_ws(
                f"/websocket/chats/{chat_id}?token={token}", client=ws_client
            ):
                pass

    assert refused.value.code == CloseCode.ACCESS_REVOKED


async def test_a_users_entry_expires_with_the_longest_token_it_could_be_blocking(
    client: AsyncClient,
):
    """No entry outlives what it blocks, which is what keeps this list from needing a keeper.

    The service cannot know when a person's outstanding tokens run out — it holds
    no record of what the monolith issued — so a user entry lives for the longest
    a token can, and not a second more.
    """
    user_id, _ = caller_token()

    await revoke(client, user_id=user_id)

    remaining = await redis_client.ttl(user_key(DEFAULT_COMPANY_ID, uuid.UUID(user_id)))
    assert 0 < remaining <= settings.chat_token_ttl_seconds


async def test_a_revocation_naming_one_token_blocks_it_and_leaves_the_person_their_access(
    client: AsyncClient,
):
    """The narrow instrument: a credential believed leaked, without locking anybody out.

    A replacement token for the same person still opens a connection, which is
    the whole difference from banning them.

    A connection already holding the leaked token is closed at its next
    revalidation rather than at once. The sockets are indexed by who holds them,
    not by which string they presented, and a third index for the rarer half of
    an exception path would earn less than it costs.
    """
    user_id, leaked = caller_token()
    # A different lifetime, because the same claims and the same whole-second
    # `exp` produce the same bytes — two tokens minted for one person inside a
    # second are one token, and this test needs two.
    _, replacement = caller_token(uuid.UUID(user_id), expires_in=timedelta(minutes=14))
    _, owner_token = caller_token()
    chat_id = await open_chat_id(client, bearer(owner_token), user_id)

    await revoke(client, token=leaked)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with pytest.raises(WebSocketDisconnect) as refused:
            async with aconnect_ws(
                f"/websocket/chats/{chat_id}?token={leaked}", client=ws_client
            ):
                pass

        async with aconnect_ws(
            f"/websocket/chats/{chat_id}?token={replacement}", client=ws_client
        ) as allowed:
            await allowed.send_json({"type": "ping", "over": "the same connection"})

    assert refused.value.code == CloseCode.ACCESS_REVOKED
    assert await redis_client.ttl(token_key(leaked)) > 0


async def test_a_revocation_that_names_both_a_user_and_a_token_is_refused(client: AsyncClient):
    """The two shapes mean different things, so a command that is both means neither.

    Banning the person already blocks every token they hold, so naming one as
    well is either a caller that misread the contract or two commands that got
    merged — and guessing which would be answering a question the monolith did
    not ask.
    """
    user_id, token = caller_token()

    response = await client.post(
        "/internal/revocations",
        json={
            "company_id": str(DEFAULT_COMPANY_ID),
            "user_id": user_id,
            "token": token,
        },
        headers=service_credential(),
    )

    assert response.status_code == 422


async def test_a_revocation_that_names_nothing_to_revoke_is_refused(client: AsyncClient):
    """At-least-once delivery makes a silent no-op the worst answer available.

    A command the monolith thought revoked something and which revoked nothing
    would be retried, succeed the same way, and be believed.
    """
    response = await client.post(
        "/internal/revocations",
        json={"company_id": str(DEFAULT_COMPANY_ID)},
        headers=service_credential(),
    )

    assert response.status_code == 422
