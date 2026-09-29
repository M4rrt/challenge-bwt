"""Every route refuses a caller who presents no credential, or is on a short, named list of routes that do not.

A route added without an authentication dependency is silently public. This
enumerates the operations the app itself publishes (`app.openapi()`) and calls
each with nothing, so that mistake fails a test instead of shipping — and a new
route is covered the day it is added, with nobody having to remember to.

It asserts behaviour, not structure: it does not look at which dependencies a
route declares (that would depend on FastAPI's routing internals and could pass
while checking nothing), it checks the answer a caller actually gets.

The WebSocket routes are not in an OpenAPI document; they authenticate in the
handler (`admit`) and are covered by `test_websocket.py`.
"""

import re
import uuid

import pytest
from httpx import AsyncClient

from app.main import app

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# Public on purpose. `/webhook/messages` authenticates by HMAC signature inside
# the handler, since its caller is an external system with no chat token.
PUBLIC_ROUTES = {"/health", "/webhook/messages"}


def _operations() -> list[tuple[str, str]]:
    return sorted(
        (method, path)
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method in HTTP_METHODS
    )


def _with_placeholders_filled(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_the_route_table_is_actually_being_enumerated():
    """Guards the test below against passing over an empty list."""
    paths = {path for _, path in _operations()}

    assert PUBLIC_ROUTES <= paths
    assert len(paths - PUBLIC_ROUTES) >= 8


@pytest.mark.parametrize(("method", "path"), [op for op in _operations() if op[1] not in PUBLIC_ROUTES])
async def test_a_route_refuses_a_caller_with_no_credential(client: AsyncClient, method: str, path: str):
    response = await client.request(method.upper(), _with_placeholders_filled(path))

    assert response.status_code == 401, f"{method.upper()} {path} answered {response.status_code} with no credential"


@pytest.mark.parametrize(("method", "path"), [op for op in _operations() if op[1] not in PUBLIC_ROUTES])
async def test_a_route_refuses_a_credential_that_is_not_a_chat_token(
    client: AsyncClient, method: str, path: str
):
    response = await client.request(
        method.upper(),
        _with_placeholders_filled(path),
        headers={"Authorization": "Bearer not-a-chat-token"},
    )

    assert response.status_code == 401, f"{method.upper()} {path} answered {response.status_code} with a bogus credential"
