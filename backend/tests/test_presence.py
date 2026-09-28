"""Presence: who is online in a Chat, kept in Redis alone.

Ticket 12. Pure Redis with no table behind it, exactly the property the source
module had, and it degrades to "unknown" rather than breaking the Chat when the
store cannot answer — messaging does not read this module at all, so a presence
outage has nothing to take down on that side.

`app/services/presence.py` is tested twice, the way the spec asks of pure logic
with a hard-to-reach branch: directly, for the ref-counting and the fail-open
contract a two-tab reconnect or a Redis outage would otherwise need a slow or
flaky end-to-end setup to exercise; and through the WebSocket, which is the
seam that proves a Chat actually announces what this module decides.
"""

import uuid

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.services import presence
from app.services.outbox import drain_once
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token
from tests.chats import open_chat_id
from tests.messages import bodies, say
from tests.sockets import receive_until

COMPANY = uuid.uuid4()
OTHER_COMPANY = uuid.uuid4()
CHAT = uuid.uuid4()


@pytest.fixture(autouse=True)
async def forget_presence():
    """Redis is not rolled back with the transaction, unlike everything else a test touches."""
    yield
    keys = [key async for key in presence.redis_client.scan_iter(match="presence:*")]
    if keys:
        await presence.redis_client.delete(*keys)


async def test_a_second_connection_from_the_same_user_does_not_repeat_the_announcement():
    user = uuid.uuid4()

    assert await presence.join(COMPANY, CHAT, user) is True
    assert await presence.join(COMPANY, CHAT, user) is False


async def test_leaving_reports_offline_only_once_the_last_connection_has_gone():
    user = uuid.uuid4()
    await presence.join(COMPANY, CHAT, user)
    await presence.join(COMPANY, CHAT, user)

    assert await presence.leave(COMPANY, CHAT, user) is False
    assert (await presence.who_is_online(COMPANY, CHAT, [user])) == [user]

    assert await presence.leave(COMPANY, CHAT, user) is True
    assert (await presence.who_is_online(COMPANY, CHAT, [user])) == []


async def test_a_failed_join_does_not_let_that_connections_disconnect_decrement_a_sibling_tab(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """The bug this guards against: a connection whose `join` never fired must not `leave` either.

    Two tabs, one person. The first tab's join succeeds ordinarily. The
    second's is made to fail — a simulated outage at the moment it connects —
    so it never increments the counter the first tab already holds at 1.
    Disconnecting the second tab must leave that count alone: before
    `Connection` tracked whether its own `join` had actually succeeded, its
    `finally` called `leave` unconditionally, decrementing a counter it had
    never incremented and reporting the first tab's person offline while that
    tab was still open.
    """
    user_a_id, token_a = caller_token()
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, bearer(token_a), user_b_id)

    store_down = False
    real_pipeline = presence.redis_client.pipeline

    def maybe_broken_pipeline(*args, **kwargs):
        if store_down:
            raise RedisError("presence store is down")
        return real_pipeline(*args, **kwargs)

    monkeypatch.setattr(presence.redis_client, "pipeline", maybe_broken_pipeline)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/chats/{chat_id}?token={token_a}", client=ws_client
        ) as steady:
            await receive_until(steady, lambda frame: frame["type"] == "presence.online")

            store_down = True
            async with aconnect_ws(
                f"/websocket/chats/{chat_id}?token={token_a}", client=ws_client
            ):
                pass  # its join failed silently; there is nothing to wait for
            store_down = False

            still_online = await presence.who_is_online(
                DEFAULT_COMPANY_ID, uuid.UUID(chat_id), [uuid.UUID(user_a_id)]
            )

    assert still_online == [uuid.UUID(user_a_id)]


async def test_presence_never_crosses_a_company():
    """Two Companies cannot collide on a real Chat id — it is one row's primary key.

    Which is exactly why this guarantee needs a direct test: the API cannot be
    asked to construct the situation the key format has to survive, so this
    proves the Company is load-bearing in `_key` the same way a unit test proves
    the default-deny branch of the Staff-only rule.
    """
    user = uuid.uuid4()
    await presence.join(COMPANY, CHAT, user)

    assert (await presence.who_is_online(COMPANY, CHAT, [user])) == [user]
    assert (await presence.who_is_online(OTHER_COMPANY, CHAT, [user])) == []


async def test_an_unreachable_store_reports_unknown_rather_than_offline(
    monkeypatch: pytest.MonkeyPatch,
):
    user = uuid.uuid4()

    async def broken(*_args, **_kwargs):
        raise RedisError("presence store is down")

    monkeypatch.setattr(presence.redis_client, "mget", broken)

    assert await presence.who_is_online(COMPANY, CHAT, [user]) is None


async def test_an_unreachable_store_fails_joining_and_leaving_open_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
):
    """`pipeline()` and `decr()` are not themselves awaited, unlike everything else here.

    A broken coroutine in their place would raise "coroutine object does not
    support ..." instead of the `RedisError` this is about, so the double here
    is a plain callable, not an `async def`.
    """
    user = uuid.uuid4()

    def broken(*_args, **_kwargs):
        raise RedisError("presence store is down")

    monkeypatch.setattr(presence.redis_client, "pipeline", broken)
    assert await presence.join(COMPANY, CHAT, user) is False

    async def broken_eval(*_args, **_kwargs):
        raise RedisError("presence store is down")

    monkeypatch.setattr(presence.redis_client, "eval", broken_eval)
    assert await presence.leave(COMPANY, CHAT, user) is False


async def test_a_connecting_participant_sees_who_is_already_online(client: AsyncClient):
    user_a_id, token_a = caller_token()
    user_b_id, token_b = caller_token()
    chat_id = await open_chat_id(client, bearer(token_a), user_b_id)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(f"/websocket/chats/{chat_id}?token={token_a}", client=ws_client) as a:
            # Waiting for A's own online echo is what makes the next connect a
            # connect into a Chat where A is *known* to be online already,
            # rather than a race against A's own join still being in flight.
            await receive_until(a, lambda frame: frame["type"] == "presence.online")

            async with aconnect_ws(
                f"/websocket/chats/{chat_id}?token={token_b}", client=ws_client
            ) as b:
                snapshot = await receive_until(
                    b, lambda frame: frame["type"] == "presence.snapshot"
                )

    assert snapshot["known"] is True
    assert snapshot["online"] == [user_a_id]


def _online(user_id: str):
    return lambda frame: frame.get("type") == "presence.online" and frame.get("user_id") == user_id


def _offline(user_id: str):
    return lambda frame: frame.get("type") == "presence.offline" and frame.get("user_id") == user_id


async def test_connecting_announces_online_to_a_participant_already_there(client: AsyncClient):
    """`_online(user_a_id)` rather than a bare `type == "presence.online"`.

    B's own connect announces B's own arrival on the same channel, so the first
    `presence.online` frame B's socket sees can be B's own — matching on whose
    it is is what makes this a test about A rather than a coin flip between the
    two.
    """
    user_a_id, token_a = caller_token()
    user_b_id, token_b = caller_token()
    chat_id = await open_chat_id(client, bearer(token_a), user_b_id)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(f"/websocket/chats/{chat_id}?token={token_b}", client=ws_client) as b:
            await receive_until(b, lambda frame: frame["type"] == "presence.snapshot")

            async with aconnect_ws(f"/websocket/chats/{chat_id}?token={token_a}", client=ws_client):
                seen = await receive_until(b, _online(user_a_id))

    assert seen["chat_id"] == chat_id


async def test_disconnecting_announces_offline_to_the_participant_left_behind(
    client: AsyncClient,
):
    user_a_id, token_a = caller_token()
    user_b_id, token_b = caller_token()
    chat_id = await open_chat_id(client, bearer(token_a), user_b_id)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(f"/websocket/chats/{chat_id}?token={token_b}", client=ws_client) as b:
            await receive_until(b, lambda frame: frame["type"] == "presence.snapshot")

            async with aconnect_ws(f"/websocket/chats/{chat_id}?token={token_a}", client=ws_client):
                await receive_until(b, _online(user_a_id))

            seen = await receive_until(b, _offline(user_a_id))

    assert seen["chat_id"] == chat_id


async def test_messaging_keeps_working_when_the_presence_store_is_unreachable(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """The acceptance criterion, at the seam a client actually uses.

    A presence outage must not be a reason a connection refuses to open, a
    snapshot raises instead of reporting `known: false`, or an ordinary send and
    read stop working — none of which presence is on the path of, which is what
    this proves rather than assumes.
    """
    user_a_id, token_a = caller_token()
    user_b_id, token_b = caller_token()
    chat_id = await open_chat_id(client, bearer(token_a), user_b_id)

    async def broken_async(*_args, **_kwargs):
        raise RedisError("presence store is down")

    def broken_sync(*_args, **_kwargs):
        raise RedisError("presence store is down")

    monkeypatch.setattr(presence.redis_client, "mget", broken_async)
    monkeypatch.setattr(presence.redis_client, "pipeline", broken_sync)
    monkeypatch.setattr(presence.redis_client, "expire", broken_async)
    monkeypatch.setattr(presence.redis_client, "eval", broken_async)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(f"/websocket/chats/{chat_id}?token={token_a}", client=ws_client) as a:
            snapshot = await a.receive_json(timeout=5)

            await say(client, chat_id, bearer(token_b), "ainda funciona")
            await drain_once(db_session)
            arrived = await a.receive_json(timeout=5)

    assert snapshot == {
        "type": "presence.snapshot",
        "chat_id": chat_id,
        "online": [],
        "known": False,
    }
    assert arrived["body"] == "ainda funciona"
    assert await bodies(client, chat_id, bearer(token_a)) == ["ainda funciona"]
