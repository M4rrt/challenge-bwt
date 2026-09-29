"""JWKS URL refresh: rotation without a redeploy, never at the cost of a request.

`verify_chat_token` never touches the network — these tests are the only place
that does, via `httpx.MockTransport`, so no real HTTP call happens in the
suite.
"""

import asyncio
import json

import httpx
import pytest

from app.core.chat_token import verify_chat_token
from app.core.config import settings
from app.services.chat_token_keys import _refresh_once, run_jwks_refresh
from tests.chat_tokens import TEST_JWKS, TEST_KEY_PAIR, mint_chat_token

import app.core.chat_token as chat_token


@pytest.fixture(autouse=True)
def restore_active_keyset(monkeypatch: pytest.MonkeyPatch):
    """Every test starts from, and leaves, the configured bootstrap keyset."""
    monkeypatch.setattr(settings, "chat_token_jwks_url", "https://monolith.test/chat-jwks.json")
    yield
    chat_token.set_active_keyset(TEST_JWKS["keys"])


ROTATED_KID = "test-chat-key-2"
ROTATED_KEY_PAIR = TEST_KEY_PAIR  # reuse the same signing key under a new kid to prove *selection*
ROTATED_JWK = {**TEST_JWKS["keys"][0], "kid": ROTATED_KID}


async def test_a_successful_fetch_replaces_the_active_keyset():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [ROTATED_JWK]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        await _refresh_once(client)

    token = mint_chat_token(kid=ROTATED_KID)
    assert verify_chat_token(token) is not None
    # The kid this service booted with is no longer in the active set: a
    # successful fetch replaces, it does not merge.
    assert verify_chat_token(mint_chat_token(kid=TEST_KEY_PAIR.kid)) is None


async def test_a_successful_but_empty_fetch_does_not_resurrect_the_bootstrap_key():
    """`{"keys": []}` is a 200, not a failure — but it must not un-revoke a key.

    A prior rotation already replaced the bootstrap `kid` with `ROTATED_KID`.
    The monolith can publish an empty key set mid-rotation; treating that as
    "fall back to whatever the service booted with" would silently re-trust a
    key the monolith has since revoked.
    """

    def rotate(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [ROTATED_JWK]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(rotate))
    async with client:
        await _refresh_once(client)

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(empty))
    async with client:
        await _refresh_once(client)

    assert verify_chat_token(mint_chat_token(kid=ROTATED_KID)) is not None
    assert verify_chat_token(mint_chat_token(kid=TEST_KEY_PAIR.kid)) is None


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(200, content=b"not json"),
        lambda request: httpx.Response(200, json={"nope": []}),
    ],
    ids=["server-error", "malformed-body", "no-keys-field"],
)
async def test_a_failed_fetch_leaves_the_active_keyset_untouched(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(Exception):  # noqa: B017 - any of httpx.HTTPError/ValueError/KeyError
        async with client:
            await _refresh_once(client)

    # The bootstrap key still verifies: the failed fetch never touched it.
    assert verify_chat_token(mint_chat_token()) is not None


async def test_the_refresh_loop_is_a_no_op_without_a_jwks_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "chat_token_jwks_url", None)
    started = asyncio.Event()

    await asyncio.wait_for(run_jwks_refresh(started), timeout=1)

    assert started.is_set()
