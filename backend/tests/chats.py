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
    return await client.post(
        "/chats",
        json={
            "type": chat_type,
            "participants": [{"user_id": uid, "user_kind": user_kind} for uid in user_ids],
            "name": name,
        },
        headers=headers,
    )


async def open_chat_id(client: AsyncClient, headers: dict[str, str], *user_ids: str) -> str:
    response = await open_chat(client, headers, *user_ids)
    return response.json()["id"]
