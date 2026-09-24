"""Ticket 08: a retry stores one message, and a deletion marks rather than removes.

Both halves are about the same thing — the row is the unit of truth and it is
never written twice and never taken away — so they are tested together, through
seam 1, the way the spec asks for idempotency and tombstone behaviour.
"""

import json
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.outbox import OutboxEvent
from app.services.outbox import drain_once
from app.services.realtime import address_for_chat, address_for_chat_staff
from tests.chats import open_chat_id, open_chat_of
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token
from tests.messages import bodies, say


async def _chat_with_two(client: AsyncClient) -> tuple[str, dict[str, str], dict[str, str]]:
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    user_b_id, token_b = caller_token()
    chat_id = await open_chat_id(client, headers_a, user_b_id)
    return chat_id, headers_a, bearer(token_b)


async def _send(
    client: AsyncClient,
    chat_id: str,
    headers: dict[str, str],
    body: str,
    client_message_id: str,
    *,
    visibility: str | None = None,
):
    """`say` with the client message id named, because that is what these tests vary."""
    return await say(
        client,
        chat_id,
        headers,
        body,
        visibility=visibility,
        client_message_id=client_message_id,
    )


async def test_a_message_carries_the_client_message_id_its_sender_supplied(
    client: AsyncClient,
):
    chat_id, headers_a, _ = await _chat_with_two(client)

    response = await _send(client, chat_id, headers_a, "oi", "retry-me")

    assert response.status_code == 201
    assert response.json()["client_message_id"] == "retry-me"


async def test_a_send_without_a_client_message_id_is_refused(client: AsyncClient):
    """Refused rather than stored without one, so idempotency cannot be lost quietly.

    A nullable column would make a client that forgot the field look exactly
    like one that sent it — right up until a retry duplicated what they said.
    """
    chat_id, headers_a, _ = await _chat_with_two(client)

    response = await client.post(
        f"/chats/{chat_id}/messages", json={"body": "oi"}, headers=headers_a
    )

    assert response.status_code == 422


async def test_the_same_client_message_id_twice_returns_the_original_message(
    client: AsyncClient,
):
    """A retry is the same message arriving again, not a second thing said.

    Answering 201 with the original rather than 409 is what makes the retry
    safe to write blindly: a client that never saw the first response has no
    way to tell the two cases apart, and an error would push it into deciding
    whether to try once more.
    """
    chat_id, headers_a, _ = await _chat_with_two(client)

    first = await _send(client, chat_id, headers_a, "oi", "retry-me")
    second = await _send(client, chat_id, headers_a, "oi", "retry-me")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


async def test_a_retried_send_stores_one_row(client: AsyncClient):
    """The thread is what proves it: the duplicate must not be readable anywhere."""
    chat_id, headers_a, _ = await _chat_with_two(client)

    await _send(client, chat_id, headers_a, "oi", "retry-me")
    await _send(client, chat_id, headers_a, "oi", "retry-me")

    assert await bodies(client, chat_id, headers_a) == ["oi"]


async def test_a_retry_answers_with_what_was_stored_not_with_what_it_resent(
    client: AsyncClient,
):
    """The first send is the one that happened; a differing retry does not edit it.

    A client whose retry carried a changed body would otherwise have found an
    edit endpoint nobody designed — and one that rewrites history silently,
    since the original is never shown again.
    """
    chat_id, headers_a, _ = await _chat_with_two(client)

    await _send(client, chat_id, headers_a, "o que eu disse", "retry-me")
    second = await _send(client, chat_id, headers_a, "outra coisa", "retry-me")

    assert second.json()["body"] == "o que eu disse"
    assert await bodies(client, chat_id, headers_a) == ["o que eu disse"]


async def test_two_senders_may_use_the_same_client_message_id(client: AsyncClient):
    """The id is the client's, so it is only unique to that client.

    Two clients generating the same value is not a retry of anything — nothing
    about one sender's numbering is a claim about another's, and collapsing
    them would silently swallow the second person's message.
    """
    chat_id, headers_a, headers_b = await _chat_with_two(client)

    from_a = await _send(client, chat_id, headers_a, "eu", "same-id")
    from_b = await _send(client, chat_id, headers_b, "e eu", "same-id")

    assert from_a.status_code == 201
    assert from_b.status_code == 201
    assert from_a.json()["id"] != from_b.json()["id"]
    assert await bodies(client, chat_id, headers_a) == ["eu", "e eu"]


async def _delete(
    client: AsyncClient,
    chat_id: str,
    message_id: str,
    headers: dict[str, str],
    reason: str | None = None,
):
    return await client.request(
        "DELETE",
        f"/chats/{chat_id}/messages/{message_id}",
        json={"reason": reason},
        headers=headers,
    )


async def test_deleting_a_message_clears_its_body(client: AsyncClient):
    chat_id, headers_a, _ = await _chat_with_two(client)
    message_id = (await _send(client, chat_id, headers_a, "engano", "m1")).json()["id"]

    deleted = await _delete(client, chat_id, message_id, headers_a, "me enganei")

    assert deleted.status_code == 200
    assert deleted.json()["body"] == ""
    assert deleted.json()["deleted_at"] is not None


async def test_deleting_a_message_records_who_deleted_it_and_why(
    client: AsyncClient, db_session: AsyncSession
):
    """Recorded on the row, not in the response.

    Who deleted it and the reason they gave are for whoever asks afterwards —
    a supervisor, an audit — and not for the thread, where the marker's whole
    message is that something was taken back.
    """
    chat_id, headers_a, _ = await _chat_with_two(client)
    sent = (await _send(client, chat_id, headers_a, "engano", "m1")).json()

    await _delete(client, chat_id, sent["id"], headers_a, "me enganei")

    stored = await db_session.get(Message, uuid.UUID(sent["id"]))
    assert stored is not None
    assert stored.deleted_at is not None
    assert stored.deleted_by_user_id == uuid.UUID(sent["sender_id"])
    assert stored.deletion_reason == "me enganei"


async def test_a_deleted_message_keeps_its_place_in_the_thread(client: AsyncClient):
    """The marker stays where it was, so the thread does not change shape.

    Removing the row would shift everything after it up, and — once paging is a
    cursor over what the row still holds — move the boundary somebody was
    already scrolled past. The deletion is visible; the gap it would leave is
    not something anyone asked for.
    """
    chat_id, headers_a, headers_b = await _chat_with_two(client)
    await _send(client, chat_id, headers_a, "um", "m1")
    middle = (await _send(client, chat_id, headers_a, "dois", "m2")).json()["id"]
    await _send(client, chat_id, headers_a, "três", "m3")

    await _delete(client, chat_id, middle, headers_a)

    assert await bodies(client, chat_id, headers_b) == ["um", "", "três"]


async def test_a_participant_cannot_delete_someone_elses_message(client: AsyncClient):
    """Forbidden, not hidden.

    The 404-not-403 rule is about not confirming that a Chat exists to somebody
    outside it. This caller is inside it and has already read the message, so
    there is nothing left to conceal and a 404 would only be a lie.
    """
    chat_id, headers_a, headers_b = await _chat_with_two(client)
    message_id = (await _send(client, chat_id, headers_a, "meu", "m1")).json()["id"]

    refused = await _delete(client, chat_id, message_id, headers_b)

    assert refused.status_code == 403
    assert await bodies(client, chat_id, headers_a) == ["meu"]


async def test_someone_outside_the_chat_cannot_delete_from_it(client: AsyncClient):
    chat_id, headers_a, _ = await _chat_with_two(client)
    message_id = (await _send(client, chat_id, headers_a, "meu", "m1")).json()["id"]
    outsider = bearer(caller_token()[1])

    refused = await _delete(client, chat_id, message_id, outsider)

    assert refused.status_code == 404


async def test_a_retry_after_a_deletion_does_not_bring_the_message_back(
    client: AsyncClient,
):
    """The two halves of this ticket meeting, and the reason the row stays.

    Delete the row instead of marking it and the sender's next retry finds
    nothing to collide with, writes the message a second time, and undoes the
    deletion on the sender's behalf — the one failure a tombstone exists to
    prevent. The retry gets the marker back, because the marker is what that
    client message id now names.
    """
    chat_id, headers_a, headers_b = await _chat_with_two(client)
    message_id = (await _send(client, chat_id, headers_a, "engano", "m1")).json()["id"]
    await _delete(client, chat_id, message_id, headers_a)

    retried = await _send(client, chat_id, headers_a, "engano", "m1")

    assert retried.json()["id"] == message_id
    assert retried.json()["body"] == ""
    assert retried.json()["deleted_at"] is not None
    assert await bodies(client, chat_id, headers_b) == [""]


async def test_deleting_without_a_body_at_all_works(client: AsyncClient):
    """The usual client call: `DELETE`, no payload, no reason.

    Optional has to mean optional at the transport too — a required body would
    make every caller send `{}` to say nothing.
    """
    chat_id, headers_a, _ = await _chat_with_two(client)
    message_id = (await _send(client, chat_id, headers_a, "engano", "m1")).json()["id"]

    deleted = await client.delete(
        f"/chats/{chat_id}/messages/{message_id}", headers=headers_a
    )

    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None


async def test_deleting_twice_keeps_the_first_deletion_on_the_row(
    client: AsyncClient, db_session: AsyncSession
):
    """The second delete changes nothing, including the reason the first gave.

    Without this a double-click unrecords the why: the second request carries no
    body, and overwriting would put a null where an explanation was and move
    `deleted_at` to the moment of the accident. A Message already taken back is
    a request that has already succeeded.
    """
    chat_id, headers_a, _ = await _chat_with_two(client)
    sent = (await _send(client, chat_id, headers_a, "engano", "m1")).json()
    first = await _delete(client, chat_id, sent["id"], headers_a, "me enganei")

    second = await client.delete(
        f"/chats/{chat_id}/messages/{sent['id']}", headers=headers_a
    )

    assert second.status_code == 200
    assert second.json()["deleted_at"] == first.json()["deleted_at"]
    stored = await db_session.get(Message, uuid.UUID(sent["id"]))
    assert stored is not None
    assert stored.deletion_reason == "me enganei"


async def _pending(db: AsyncSession) -> list[OutboxEvent]:
    result = await db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at)
    )
    return list(result.all())


async def test_deleting_a_message_announces_the_marker_to_the_chat(
    client: AsyncClient, db_session: AsyncSession
):
    """Everyone shown the Message is told it is gone, without asking again.

    Without this the deletion is only true for whoever is next to reload: every
    socket already open keeps showing the body the author just took back, which
    is the one moment they were promised it would stop being visible.
    """
    chat_id, headers_a, _ = await _chat_with_two(client)
    message_id = (await _send(client, chat_id, headers_a, "engano", "m1")).json()["id"]
    await drain_once(db_session)

    await _delete(client, chat_id, message_id, headers_a)

    announced = await _pending(db_session)
    assert [event.address for event in announced] == [
        address_for_chat(DEFAULT_COMPANY_ID, uuid.UUID(chat_id)).channel
    ]
    marker = json.loads(announced[0].payload)
    assert marker["id"] == message_id
    assert marker["body"] == ""
    assert marker["deleted_at"] is not None


async def test_deleting_a_staff_only_message_is_announced_only_to_staff(
    client: AsyncClient, db_session: AsyncSession
):
    """The end client is not told that something they cannot name has gone.

    This is the branch `_address_of` exists for. Announced on the Chat's own
    address instead, the tombstone would arrive on the end client's socket
    carrying the identifier of a Message they were never shown — teaching them
    a Staff-only Message existed at the moment it stopped existing, which is
    exactly the leak ticket 04 forbids.
    """
    _, token_a = caller_token()
    headers_a = bearer(token_a)
    staff_b_id, _ = caller_token()
    client_c_id, _ = caller_token(user_kind="client")
    chat_id = (
        await open_chat_of(
            client,
            headers_a,
            (staff_b_id, "staff"),
            (client_c_id, "client"),
            chat_type="client",
            name="Cliente e equipe",
        )
    ).json()["id"]
    secret_id = (
        await _send(client, chat_id, headers_a, "segredo", "m1", visibility="staff_only")
    ).json()["id"]
    await drain_once(db_session)

    await _delete(client, chat_id, secret_id, headers_a)

    announced = await _pending(db_session)
    assert [event.address for event in announced] == [
        address_for_chat_staff(DEFAULT_COMPANY_ID, uuid.UUID(chat_id)).channel
    ]
    assert (
        address_for_chat(DEFAULT_COMPANY_ID, uuid.UUID(chat_id)).channel
        not in {event.address for event in announced}
    )
