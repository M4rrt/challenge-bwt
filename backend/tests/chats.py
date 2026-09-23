"""Opening a Chat over the API, without every test restating the command's shape.

Three test modules used to carry their own copy of this, so each change to the
create command was a change in four places — which is how a payload shape ends
up being asserted by nobody in particular.
"""

from httpx import AsyncClient, Response


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
    """
    return await client.post(
        "/chats",
        json={
            "type": chat_type,
            "participants": [
                {"user_id": user_id, "user_kind": kind} for user_id, kind in members
            ],
            "name": name,
        },
        headers=headers,
    )


async def open_chat_id(client: AsyncClient, headers: dict[str, str], *user_ids: str) -> str:
    response = await open_chat(client, headers, *user_ids)
    return response.json()["id"]
