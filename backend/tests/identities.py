"""Driving the identity ingress the way the monolith does.

The projection has three inbound writes and two of them are routes nobody else
in the suite calls, so their payload shape would otherwise be restated by each
test that happened to need one — which is how a wire contract ends up asserted
by nobody in particular. `tests/chats.py` exists for the same reason and reads
the same way.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from httpx import AsyncClient, Response

from tests.chats import open_chat, service_credential
from tests.chat_tokens import DEFAULT_COMPANY_ID, bearer, caller_token


def now() -> datetime:
    return datetime.now(timezone.utc)


def snapshot(
    user_id: str,
    *,
    display_name: str,
    avatar_url: str | None = None,
    user_kind: str = "staff",
    company_id: str | None = None,
    source_updated_at: datetime | None = None,
) -> dict[str, object]:
    """One identity as the monolith last knew it, and when it last knew it."""
    return {
        "user_id": user_id,
        "company_id": company_id or str(DEFAULT_COMPANY_ID),
        "user_kind": user_kind,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "source_updated_at": (source_updated_at or now()).isoformat(),
    }


async def identity_event(
    client: AsyncClient,
    user_id: str,
    *,
    event_id: str | None = None,
    display_name: str,
    avatar_url: str | None = None,
    user_kind: str = "staff",
    company_id: str | None = None,
    source_updated_at: datetime | None = None,
) -> Response:
    """One identity change, on the internal ingress.

    A snapshot and nothing else: creation, change, deactivation and
    anonymisation are all the monolith describing a user differently, and a
    projection that stored the verb would store something no response reads.
    """
    return await client.post(
        "/internal/identity-events",
        json={
            "event_id": event_id or str(uuid.uuid4()),
            **snapshot(
                user_id,
                display_name=display_name,
                avatar_url=avatar_url,
                user_kind=user_kind,
                company_id=company_id,
                source_updated_at=source_updated_at,
            ),
        },
        headers=service_credential(),
    )


async def bulk_load(client: AsyncClient, *identities: dict[str, object]) -> Response:
    """Initial population and rebuild, which is the third and last inbound write.

    The same snapshot the event stream carries, minus the event id, because a
    rebuild is not something that happened — it is the monolith stating what is
    true for a set of users at once.
    """
    return await client.post(
        "/internal/identities",
        json={"identities": list(identities)},
        headers=service_credential(),
    )


def naive_now() -> datetime:
    """A timestamp carrying no zone, which is what a careless emitter sends."""
    return datetime.now()


async def a_chat_with_one_message(
    client: AsyncClient, *, sender_is_called: str = "Carla Dias"
) -> tuple[str, Callable[[], Awaitable[list[str]]]]:
    """A message sent by one person and readable by another, which is the fixture.

    Every test of this projection needs the same three things: somebody with a
    name the monolith gave them, a message they sent, and a *different* reader
    whose own token says nothing about them — because a name that could have
    come from the reader's token proves nothing about the projection.

    Returns the sender's identifier and a way to ask the reader who the thread
    says spoke, which is the question every one of these tests ends on.
    """
    sender_id, sender_token = caller_token(display_name=sender_is_called)
    reader_id, reader_token = caller_token(display_name="Bruno Lima")

    chat_id = (await open_chat(client, bearer(sender_token), reader_id)).json()["id"]
    await client.post(
        f"/chats/{chat_id}/messages",
        json={"body": "bom dia"},
        headers=bearer(sender_token),
    )

    async def sender_names() -> list[str]:
        read = await client.get(
            f"/chats/{chat_id}/messages", headers=bearer(reader_token)
        )
        return [message["sender_display_name"] for message in read.json()]

    return sender_id, sender_names
