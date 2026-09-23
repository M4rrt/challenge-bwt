"""The outbox and its drain: seam 2.

The request no longer publishes, so the HTTP seam alone can no longer observe
realtime. Tests send through HTTP, run one drain tick, and assert on what came
out — which is exactly what the production drain process does in a loop.
"""

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent
from app.services import outbox as app_outbox
from app.services.outbox import drain_once, oldest_unpublished_age
from app.services.realtime import address_for_chat, address_for_user
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token
from tests.chats import open_chat_id


async def _pending(db: AsyncSession) -> list[OutboxEvent]:
    result = await db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at)
    )
    return list(result.all())


async def test_sending_a_message_enqueues_it_for_the_chat_and_for_each_participant(
    client: AsyncClient, db_session: AsyncSession
):
    """One address carries the message, another carries "this Chat moved".

    Both were published inside the request before. Writing them instead is what
    makes a rolled-back send announce nothing, and what lets a process that dies
    after the commit still owe a delivery it can be made to pay.
    """
    user_a_id, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    await client.post(
        f"/chats/{chat_id}/messages", json={"body": "oi"}, headers=headers_a
    )

    addresses = {row.address for row in await _pending(db_session)}

    assert address_for_chat(DEFAULT_COMPANY_ID, uuid.UUID(chat_id)).channel in addresses
    assert address_for_user(DEFAULT_COMPANY_ID, uuid.UUID(user_a_id)).channel in addresses
    assert address_for_user(DEFAULT_COMPANY_ID, uuid.UUID(user_b_id)).channel in addresses


async def test_a_send_that_fails_midway_leaves_neither_the_message_nor_its_announcement(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """The announcement lives and dies with the Message, because they share a transaction.

    This is what would break first if anyone put a commit between writing the
    Message and writing what announces it: the Message would survive a failure
    the announcement did not, and the Chat would hold a message nobody was ever
    told about. Failing *after* the Message is persisted and *before* the
    summaries are is the only arrangement that can tell the two apart.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)
    await drain_once(db_session)

    async def fails(*_args, **_kwargs) -> None:
        raise RuntimeError("the summaries could not be written")

    monkeypatch.setattr("app.services.message.enqueue_chat_summaries", fails)

    with pytest.raises(RuntimeError):
        await client.post(
            f"/chats/{chat_id}/messages", json={"body": "nunca aconteceu"}, headers=headers_a
        )
    await db_session.rollback()

    backlog = await client.get(f"/chats/{chat_id}/messages", headers=headers_a)

    assert backlog.json() == []
    assert await drain_once(db_session) == 0


async def test_a_drain_that_dies_mid_batch_delivers_the_rest_on_its_next_run(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Publish, then mark — so a crash in between costs a duplicate, never a loss.

    The row that was being published when the process died is still pending, so
    the next run sends it again. That is the at-least-once trade: a frame the
    reader sees twice is visible and can be deduplicated by message id, while a
    frame nobody sends is neither. Marking first would invert it.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)
    await drain_once(db_session)

    for body in ("um", "dois", "três"):
        await client.post(
            f"/chats/{chat_id}/messages", json={"body": body}, headers=headers_a
        )
    enqueued = len(await _pending(db_session))

    published: list[str] = []
    real_publish = app_outbox.publish

    async def dies_on_the_third(channel: str, payload: str) -> None:
        if len(published) == 2:
            raise ConnectionError("redis went away")
        published.append(channel)
        await real_publish(channel, payload)

    monkeypatch.setattr(app_outbox, "publish", dies_on_the_third)

    with pytest.raises(ConnectionError):
        await drain_once(db_session)
    await db_session.rollback()

    monkeypatch.setattr(app_outbox, "publish", real_publish)
    delivered_after = await drain_once(db_session)

    assert len(published) == 2
    assert delivered_after == enqueued - 2
    assert await _pending(db_session) == []


async def test_the_age_of_the_oldest_unpublished_row_is_observable(
    client: AsyncClient, db_session: AsyncSession
):
    """The realtime health signal: how far behind delivery is, not how much of it there is.

    An age rather than a count, because a thousand rows written a second ago is
    a busy service and one row written ten minutes ago is a drain that has
    stopped, and a count cannot tell those apart. Ticket 18 turns this into
    something monitored; here it only has to be answerable.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)

    owed = await oldest_unpublished_age(db_session)
    await drain_once(db_session)
    owed_nothing = await oldest_unpublished_age(db_session)

    await client.post(
        f"/chats/{chat_id}/messages", json={"body": "oi"}, headers=headers_a
    )
    owed_again = await oldest_unpublished_age(db_session)

    assert owed is not None and owed >= timedelta(0)
    assert owed_nothing is None
    assert owed_again is not None


async def test_what_a_request_enqueues_survives_the_end_of_that_request(
    client: AsyncClient, db_session: AsyncSession
):
    """The rows have to be committed by the request, not left open for the drain to commit.

    In production `get_db` closes the session when the response is done, and a
    session closed with an open transaction rolls it back. A path that enqueues
    *after* its own commit therefore writes rows that never exist — and the test
    suite cannot see it, because the drain runs on the same session here and its
    commit adopts them.

    Rolling back before draining is what removes that cover: it discards
    anything the request left uncommitted, exactly as closing the session would,
    so only rows the request itself committed are still here.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, _ = caller_token()

    chat_id = await open_chat_id(client, headers_a, user_b_id)
    await db_session.rollback()
    after_creating = await _pending(db_session)

    await client.post(
        f"/chats/{chat_id}/messages", json={"body": "oi"}, headers=headers_a
    )
    await db_session.rollback()
    after_sending = await _pending(db_session)

    assert after_creating != [], "creating a Chat announced nothing that outlived the request"
    assert len(after_sending) > len(after_creating), "sending a message announced nothing"
