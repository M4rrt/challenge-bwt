"""Supervisor reading: a Company's Chats, read without joining any of them.

Ticket 13. The scope is resolved in the monolith against a permission system
this service does not know, and arrives as a claim
(`app.core.chat_token.SUPERVISION_SCOPE`) on an otherwise ordinary token — a
Supervisor's `user_kind` is still `staff` or `client`, per the ticket's own
note, so the Staff-only Message rule never needs a third branch for them.
"""

import uuid
from datetime import datetime, timezone

from httpx import AsyncClient

from app.core.chat_token import SUPERVISION_SCOPE
from tests.chat_tokens import bearer, caller_token
from tests.chats import chat_ids, open_chat
from tests.messages import say


async def test_a_supervisor_sees_a_chat_they_are_not_a_participant_of(
    client: AsyncClient,
):
    """The ticket's opening sentence: audit or assist without joining every thread.

    A Company of its own rather than the shared default: the dev database
    carries leftover Chats under the default Company from manual testing, and
    a query that finally reads the whole Company rather than one caller's
    Participant rows is the first one in this suite that would see them.
    """
    company_id = uuid.uuid4()
    _, staff_token = caller_token(company_id=company_id)
    _, other_staff_token = caller_token(company_id=company_id)
    chat_id = (
        await open_chat(
            client, bearer(staff_token), str(uuid.uuid4()), chat_type="staff"
        )
    ).json()["id"]
    _, supervisor_token = caller_token(
        company_id=company_id, scopes=["chat:read", SUPERVISION_SCOPE]
    )

    assert await chat_ids(client, bearer(supervisor_token)) == [chat_id]
    # An ordinary staff member with no supervision scope, in the same Company
    # but no Participant of the Chat, sees nothing — the contrast the next
    # ticket criterion is about.
    assert await chat_ids(client, bearer(other_staff_token)) == []


async def test_supervised_reading_produces_no_read_receipt(client: AsyncClient):
    """Not a Participant, so there is no row for a watermark to live on.

    CONTEXT.md's own definition of Supervisor: because they are not a
    Participant, their reading never produces a read receipt. Marking as read
    needs a Participant row (`read_state._participant_in`), and a Supervisor
    has none in a Chat they only supervise — so the same refusal an outsider
    gets is the refusal that keeps a Supervisor's presence from looking like
    participation.
    """
    company_id = uuid.uuid4()
    _, staff_token = caller_token(company_id=company_id)
    chat_id = (
        await open_chat(
            client, bearer(staff_token), str(uuid.uuid4()), chat_type="staff"
        )
    ).json()["id"]
    await say(client, chat_id, bearer(staff_token), "oi")
    _, supervisor_token = caller_token(
        company_id=company_id, scopes=["chat:read", SUPERVISION_SCOPE]
    )

    refused = await client.post(
        f"/chats/{chat_id}/read",
        json={"read_at": datetime.now(timezone.utc).isoformat()},
        headers=bearer(supervisor_token),
    )

    assert refused.status_code == 404


async def test_a_supervisor_reads_the_history_of_a_chat_they_are_not_in(
    client: AsyncClient,
):
    """Auditing a thread means reading what was said in it, not just that it exists."""
    company_id = uuid.uuid4()
    _, staff_token = caller_token(company_id=company_id)
    chat_id = (
        await open_chat(
            client, bearer(staff_token), str(uuid.uuid4()), chat_type="staff"
        )
    ).json()["id"]
    await say(client, chat_id, bearer(staff_token), "combinado com o cliente")
    _, supervisor_token = caller_token(
        company_id=company_id, scopes=["chat:read", SUPERVISION_SCOPE]
    )

    history = await client.get(
        f"/chats/{chat_id}/messages", headers=bearer(supervisor_token)
    )

    assert history.status_code == 200
    assert [m["body"] for m in history.json()["messages"]] == ["combinado com o cliente"]


async def test_supervision_never_crosses_a_company(client: AsyncClient):
    """The scope grants reading inside one Company, and the Company is the token's own.

    A Supervisor's token still carries exactly one `company_id`, same as
    everyone else's, and `CompanyScope.of` reads it from the same claim
    regardless of the scopes beside it — so there is no second parameter a
    supervision claim could use to name a different Company than the one the
    token itself is scoped to.
    """
    company_x = uuid.uuid4()
    company_y = uuid.uuid4()
    _, staff_in_x = caller_token(company_id=company_x)
    chat_id = (
        await open_chat(client, bearer(staff_in_x), str(uuid.uuid4()), chat_type="staff")
    ).json()["id"]
    await say(client, chat_id, bearer(staff_in_x), "so em X")
    _, supervisor_in_y = caller_token(
        company_id=company_y, scopes=["chat:read", SUPERVISION_SCOPE]
    )

    listed = await chat_ids(client, bearer(supervisor_in_y))
    history = await client.get(
        f"/chats/{chat_id}/messages", headers=bearer(supervisor_in_y)
    )
    never_existed = await client.get(
        f"/chats/{uuid.uuid4()}/messages", headers=bearer(supervisor_in_y)
    )

    assert listed == []
    assert history.status_code == 404
    assert (history.status_code, history.json()) == (
        never_existed.status_code,
        never_existed.json(),
    )


async def test_a_staff_supervisor_reads_a_staff_only_message_like_any_staff_reader(
    client: AsyncClient,
):
    """`may_read` decides this, asked the same way it is asked for a Participant.

    The ticket's own note: reusing `may_read` for a Supervisor only works if
    their token still carries `user_kind: "staff"` — supervision adds a scope
    on top of an ordinary kind, it does not replace one. This is `may_read`
    answering `True` for that kind in a Client Chat, reached through the
    Supervisor's own gate rather than through Participation.
    """
    company_id = uuid.uuid4()
    _, staff_token = caller_token(company_id=company_id, user_kind="staff")
    end_client_id, _ = caller_token(company_id=company_id, user_kind="client")
    chat_id = (
        await open_chat(
            client,
            bearer(staff_token),
            end_client_id,
            chat_type="client",
            user_kind="client",
        )
    ).json()["id"]
    await say(client, chat_id, bearer(staff_token), "combinado", visibility="staff_only")
    _, staff_supervisor_token = caller_token(
        company_id=company_id, user_kind="staff", scopes=["chat:read", SUPERVISION_SCOPE]
    )

    seen = await client.get(
        f"/chats/{chat_id}/messages", headers=bearer(staff_supervisor_token)
    )

    assert [m["body"] for m in seen.json()["messages"]] == ["combinado"]


async def test_a_client_kind_supervisor_still_cannot_read_a_staff_only_message(
    client: AsyncClient,
):
    """Supervision is a scope on top of a kind, not a substitute for one.

    An end client granted the supervision scope by mistake is still an end
    client to `may_read` — the predicate takes the kind from the token, and
    supervision does not change what kind it says. This is the "not a bypass"
    criterion from the other side: access follows the ordinary rule even when
    the caller can reach Chats they are not a Participant of.
    """
    company_id = uuid.uuid4()
    _, staff_token = caller_token(company_id=company_id, user_kind="staff")
    client_supervisor_id, client_supervisor_token = caller_token(
        company_id=company_id, user_kind="client", scopes=["chat:read", SUPERVISION_SCOPE]
    )
    chat_id = (
        await open_chat(
            client,
            bearer(staff_token),
            client_supervisor_id,
            chat_type="client",
            user_kind="client",
        )
    ).json()["id"]
    await say(client, chat_id, bearer(staff_token), "visivel")
    await say(client, chat_id, bearer(staff_token), "interno", visibility="staff_only")

    seen = await client.get(
        f"/chats/{chat_id}/messages", headers=bearer(client_supervisor_token)
    )

    assert [m["body"] for m in seen.json()["messages"]] == ["visivel"]


async def test_an_unclassifiable_reader_kind_reads_nothing_even_with_supervision(
    client: AsyncClient,
):
    """Default-deny reaches the Supervisor's gate too — supervision is not a bypass of it.

    A token claiming a `user_kind` `ParticipantRole` cannot classify falls into
    `may_read`'s default-deny branch for every visibility, ordinary messages
    included. Ticket 13's own comment: if the monolith ever issued
    `user_kind: "supervisor"` instead of the scope, this is the loud, empty
    result the design prefers to a leak — proven here by request rather than by
    reasoning about the predicate alone.
    """
    company_id = uuid.uuid4()
    _, staff_token = caller_token(company_id=company_id, user_kind="staff")
    chat_id = (
        await open_chat(client, bearer(staff_token), str(uuid.uuid4()), chat_type="staff")
    ).json()["id"]
    await say(client, chat_id, bearer(staff_token), "oi")
    _, unclassifiable_supervisor_token = caller_token(
        company_id=company_id,
        user_kind="supervisor",
        scopes=["chat:read", SUPERVISION_SCOPE],
    )

    seen = await client.get(
        f"/chats/{chat_id}/messages", headers=bearer(unclassifiable_supervisor_token)
    )

    assert seen.json()["messages"] == []


async def test_a_caller_without_the_scope_reads_no_history_they_are_not_a_participant_of(
    client: AsyncClient,
):
    """The Supervisor's gate is additive: without the scope, `chat_of_participant` still guards.

    `test_a_supervisor_sees_a_chat_they_are_not_a_participant_of` already pins
    this down for the chat list; this is the same criterion for message
    history, which is the read `chat_for_reading` had to grow a branch in.
    """
    company_id = uuid.uuid4()
    _, staff_token = caller_token(company_id=company_id)
    _, other_staff_token = caller_token(company_id=company_id)
    chat_id = (
        await open_chat(
            client, bearer(staff_token), str(uuid.uuid4()), chat_type="staff"
        )
    ).json()["id"]
    await say(client, chat_id, bearer(staff_token), "oi")

    refused = await client.get(
        f"/chats/{chat_id}/messages", headers=bearer(other_staff_token)
    )

    assert refused.status_code == 404
