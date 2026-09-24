"""Opening a Chat the way the monolith does, without every test restating the command.

Three test modules used to carry their own copy of this, so each change to the
create command was a change in four places — which is how a payload shape ends
up being asserted by nobody in particular.

Since ticket 05 a Chat is composed by a command on the internal ingress, not by
a browser, so what these helpers send is a command. The call sites still read as
"A opens a Chat with B", which is what those tests are about; `acting_user`
below is how the person's token becomes the identity the monolith would be
acting for.
"""

from httpx import AsyncClient, Response

from app.core.chat_token import Caller, verify_chat_token
from app.core.config import settings
from tests.chat_tokens import DEFAULT_COMPANY_ID


def service_credential() -> dict[str, str]:
    """What the monolith holds, and nobody else does."""
    return {"Authorization": f"Bearer {settings.internal_service_token}"}


def acting_for(user_id: str, company_id: str) -> dict[str, str]:
    """A command's whole authority: the credential, and the user it is sent for."""
    return service_credential() | {
        "X-Acting-User": user_id,
        "X-Acting-Company": company_id,
    }


def identity(
    user_id: str,
    user_kind: str = "staff",
    *,
    company_id: str | None = None,
    display_name: str = "Ana Souza",
    avatar_url: str | None = None,
) -> dict[str, object]:
    """One Participant as the monolith knows them, having just validated them."""
    return {
        "user_id": user_id,
        "company_id": company_id or str(DEFAULT_COMPANY_ID),
        "user_kind": user_kind,
        "display_name": display_name,
        "avatar_url": avatar_url,
    }


def acting_user(headers: dict[str, str]) -> Caller:
    """Who these headers belong to, as the monolith would know them.

    Tests hold a chat token because that is how they say "as this person"; the
    monolith holds the same identity from having just validated it against live
    data. Reading it back out here keeps every call site telling its own story —
    A opens a Chat with B — while what actually goes out is a command.
    """
    caller = verify_chat_token(headers["Authorization"].removeprefix("Bearer "))
    assert caller is not None, "the monolith only sends commands for users it could identify"
    return caller


async def open_chat(
    client: AsyncClient,
    headers: dict[str, str],
    *user_ids: str,
    chat_type: str = "staff",
    user_kind: str = "staff",
    name: str | None = None,
) -> Response:
    """A Chat whose named members all share one user kind, which is the common case."""
    return await open_chat_of(
        client,
        headers,
        *((user_id, user_kind) for user_id in user_ids),
        chat_type=chat_type,
        name=name,
    )


async def open_chat_of(
    client: AsyncClient,
    headers: dict[str, str],
    *members: tuple[str, str],
    chat_type: str = "staff",
    name: str | None = None,
) -> Response:
    """A Chat whose members are named one at a time, each with their own user kind.

    A Client Chat that the visibility rule is worth testing in has both kinds
    in it at once, which the single-kind spelling above cannot express.

    The acting user is put in the Chat as well, with the kind their token
    carries. The command itself has no such rule — it names everyone, and the
    service adds nobody — but "A opens a Chat with B" means a Chat with A in it,
    and that is the sentence these tests are written in.
    """
    actor = acting_user(headers)
    return await client.post(
        "/internal/chats",
        json={
            "type": chat_type,
            "participants": [
                identity(
                    str(actor.id),
                    actor.user_kind,
                    company_id=str(actor.company_id),
                    display_name=actor.display_name or "Ana Souza",
                ),
                *(
                    identity(user_id, kind, company_id=str(actor.company_id))
                    for user_id, kind in members
                ),
            ],
            "name": name,
        },
        headers=acting_for(str(actor.id), str(actor.company_id)),
    )


async def open_chat_with(
    client: AsyncClient,
    headers: dict[str, str],
    user_id: str,
    *,
    called: str,
    user_kind: str = "staff",
    chat_type: str = "staff",
) -> Response:
    """A 1:1 with one person the command names *and* describes.

    `open_chat` above lets every Participant take the same default name, which
    is fine while nothing reads one. Ticket 10 filters the list by exactly that
    column, so the tests that do need each person to be somebody in particular
    — otherwise a search either matches everybody or matches by accident.
    """
    actor = acting_user(headers)
    return await client.post(
        "/internal/chats",
        json={
            "type": chat_type,
            "participants": [
                identity(
                    str(actor.id),
                    actor.user_kind,
                    company_id=str(actor.company_id),
                    display_name=actor.display_name or "Ana Souza",
                ),
                identity(
                    user_id,
                    user_kind,
                    company_id=str(actor.company_id),
                    display_name=called,
                ),
            ],
            "name": None,
        },
        headers=acting_for(str(actor.id), str(actor.company_id)),
    )


async def open_chat_id(client: AsyncClient, headers: dict[str, str], *user_ids: str) -> str:
    response = await open_chat(client, headers, *user_ids)
    return response.json()["id"]


async def listed(
    client: AsyncClient, headers: dict[str, str], **params: str | int | None
) -> Response:
    """The caller's chat list, with whatever this test is filtering or paging by.

    Since ticket 10 the list answers with a page rather than a bare array, and
    takes `search`, `before` and `limit`. Spelled here so that the next
    parameter is one edit rather than one per call site — which is the argument
    `say` above already makes about the send contract.

    A None is left out rather than sent. httpx would send it as an empty
    string, and an empty cursor is a string this service did not issue — so a
    test walking a list to its end would be refused on the request that starts
    the walk, for a reason that has nothing to do with what it is testing.
    """
    given = {name: value for name, value in params.items() if value is not None}
    return await client.get("/chats", params=given, headers=headers)


async def chat_ids(
    client: AsyncClient, headers: dict[str, str], **params: str | int | None
) -> list[str]:
    """Which Chats this caller sees, in order — the list's usual assertion."""
    response = await listed(client, headers, **params)
    assert response.status_code == 200, response.text
    return [chat["id"] for chat in response.json()["chats"]]
