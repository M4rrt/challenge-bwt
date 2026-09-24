"""Saying something in a Chat, without every test restating the send contract.

The same argument `tests/chats.py` makes about composition, now that sending has
a required field of its own: a dozen modules each spelling out the request body
meant that adding `client_message_id` was a change in a dozen places, and the
twelfth would have been the one nobody updated.

`client_message_id` defaults to a fresh value per call, which is what the call
sites want — each `say` is its own message. A test about retries names the id
instead, and that naming is the whole of what it is testing.
"""

import uuid

from httpx import AsyncClient, Response


async def say(
    client: AsyncClient,
    chat_id: str,
    headers: dict[str, str],
    body: str,
    *,
    visibility: str | None = None,
    client_message_id: str | None = None,
) -> Response:
    payload: dict[str, str] = {
        "body": body,
        "client_message_id": client_message_id or uuid.uuid4().hex,
    }
    if visibility is not None:
        payload["visibility"] = visibility
    return await client.post(
        f"/chats/{chat_id}/messages", json=payload, headers=headers
    )


async def bodies(client: AsyncClient, chat_id: str, headers: dict[str, str]) -> list[str]:
    """What this reader sees in the Chat, in order — the backlog's usual assertion."""
    response = await client.get(f"/chats/{chat_id}/messages", headers=headers)
    assert response.status_code == 200
    return [message["body"] for message in response.json()]
