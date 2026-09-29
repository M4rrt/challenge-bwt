"""Keeping the service's trusted key set current with what the monolith publishes.

`verify_chat_token` (`app/core/chat_token.py`) never touches the network — the
service boots and verifies against `CHAT_TOKEN_JWKS` alone, with no dependency
on this module ever running successfully. This is the opportunistic half of
key rotation: a background loop, in the same lifespan-managed-task shape as
`run_subscriber` (`app/services/realtime.py`), that polls `CHAT_TOKEN_JWKS_URL`
and hands a successful fetch to `set_active_keyset`.

A fetch failing — network, non-200, a body with no `keys` — never raises out
of the loop and never touches the active key set: `set_active_keyset` is only
ever called with a fetch that already succeeded, so "last known good" is
simply "whatever the most recent successful call passed it."
"""

import asyncio
import logging

import httpx

from app.core.chat_token import set_active_keyset
from app.core.config import settings

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 300


async def _refresh_once(client: httpx.AsyncClient) -> None:
    response = await client.get(settings.chat_token_jwks_url)
    response.raise_for_status()
    set_active_keyset(response.json()["keys"])


async def run_jwks_refresh(
    started: asyncio.Event | None = None, *, transport: httpx.BaseTransport | None = None
) -> None:
    """No `CHAT_TOKEN_JWKS_URL` configured is a valid, permanent no-op.

    `started` is set on the first attempt regardless of outcome, so a
    misconfigured or unreachable URL never blocks the service from becoming
    ready — the same "boots with no network" guarantee `chat_token.py` itself
    provides.
    """
    if not settings.chat_token_jwks_url:
        if started is not None:
            started.set()
        return

    async with httpx.AsyncClient(transport=transport, timeout=5.0) as client:
        while True:
            try:
                await _refresh_once(client)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                logger.warning("could not refresh the chat token JWKS: %s", exc)
            if started is not None:
                started.set()
                started = None
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
