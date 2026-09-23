"""The Company boundary, exercised from the outside.

ADR-0007 moved Company isolation out of the database and into code and named
that the central risk of the architecture. This file is the floor under it: one
test per read path, and a structural test that fails if a new read path is
built without going through the scope constructor.
"""

import ast
import hashlib
import hmac
import importlib
import json
import pkgutil
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.core.config import settings
from app.main import app
from tests.chat_tokens import OMITTED, bearer, caller_token


def _signed(payload: dict[str, str]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    signature = hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Signature": signature, "Content-Type": "application/json"}


async def test_chat_list_does_not_cross_company(client: AsyncClient):
    company_x = uuid.uuid4()
    company_y = uuid.uuid4()
    _, token_a = caller_token(company_id=company_x)
    user_b_id = uuid.uuid4()
    _, token_b_in_x = caller_token(user_id=user_b_id, company_id=company_x)
    _, token_b_in_y = caller_token(user_id=user_b_id, company_id=company_y)

    await client.post(
        "/conversations",
        json={"participant_user_ids": [str(user_b_id)]},
        headers=bearer(token_a),
    )

    inside = await client.get("/conversations", headers=bearer(token_b_in_x))
    outside = await client.get("/conversations", headers=bearer(token_b_in_y))

    assert len(inside.json()) == 1
    assert outside.json() == []


async def test_message_list_does_not_cross_company(client: AsyncClient):
    company_x = uuid.uuid4()
    company_y = uuid.uuid4()
    _, token_a = caller_token(company_id=company_x)
    user_b_id = uuid.uuid4()
    _, token_b_in_x = caller_token(user_id=user_b_id, company_id=company_x)
    _, token_b_in_y = caller_token(user_id=user_b_id, company_id=company_y)

    created = await client.post(
        "/conversations",
        json={"participant_user_ids": [str(user_b_id)]},
        headers=bearer(token_a),
    )
    chat_id = created.json()["id"]
    await client.post(
        f"/conversations/{chat_id}/messages",
        json={"body": "interno"},
        headers=bearer(token_a),
    )

    inside = await client.get(f"/conversations/{chat_id}/messages", headers=bearer(token_b_in_x))
    outside = await client.get(f"/conversations/{chat_id}/messages", headers=bearer(token_b_in_y))
    never_existed = await client.get(
        f"/conversations/{uuid.uuid4()}/messages", headers=bearer(token_b_in_y)
    )

    assert len(inside.json()) == 1
    assert outside.status_code == 404
    assert (outside.status_code, outside.json()) == (
        never_existed.status_code,
        never_existed.json(),
    )


async def test_opening_a_one_to_one_does_not_reuse_another_companys_chat(client: AsyncClient):
    company_x = uuid.uuid4()
    company_y = uuid.uuid4()
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    _, token_a_in_x = caller_token(user_id=user_a_id, company_id=company_x)
    _, token_a_in_y = caller_token(user_id=user_a_id, company_id=company_y)

    in_x = await client.post(
        "/conversations",
        json={"participant_user_ids": [str(user_b_id)]},
        headers=bearer(token_a_in_x),
    )
    in_y = await client.post(
        "/conversations",
        json={"participant_user_ids": [str(user_b_id)]},
        headers=bearer(token_a_in_y),
    )

    assert in_x.json()["id"] != in_y.json()["id"]


async def test_webhook_does_not_cross_company(client: AsyncClient):
    company_x = uuid.uuid4()
    company_y = uuid.uuid4()
    _, token_a = caller_token(company_id=company_x)
    created = await client.post(
        "/conversations",
        json={"participant_user_ids": [str(uuid.uuid4())]},
        headers=bearer(token_a),
    )
    chat_id = created.json()["id"]

    wrong_body, wrong_headers = _signed(
        {"company_id": str(company_y), "conversation_id": chat_id, "body": "de fora"}
    )
    unknown_body, unknown_headers = _signed(
        {"company_id": str(company_y), "conversation_id": str(uuid.uuid4()), "body": "de fora"}
    )
    right_body, right_headers = _signed(
        {"company_id": str(company_x), "conversation_id": chat_id, "body": "de dentro"}
    )

    refused = await client.post("/webhook/messages", content=wrong_body, headers=wrong_headers)
    never_existed = await client.post(
        "/webhook/messages", content=unknown_body, headers=unknown_headers
    )
    accepted = await client.post("/webhook/messages", content=right_body, headers=right_headers)

    assert refused.status_code == 404
    assert (refused.status_code, refused.json()) == (
        never_existed.status_code,
        never_existed.json(),
    )
    assert accepted.status_code == 201


def _scoped_model_names() -> set[str]:
    """Every mapped class that carries a Company, found rather than listed.

    A hand-written list is a list that goes stale: the entity somebody adds next
    has to appear here or the guard below waves it through in silence. Importing
    every module under `app.models` and reading the mapper registry means a new
    scoped entity is covered the moment it is mapped.
    """
    import app.models
    from app.core.company_scope import CompanyScoped
    from app.db import Base

    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{module.name}")

    names = {
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, CompanyScoped)
    }
    assert names, "found no company-scoped models, so the guard below would pass vacuously"
    return names


def _opens_a_read(call: ast.Call) -> list[ast.expr] | None:
    """The arguments of a call that starts a read, or None if it does not start one.

    Four shapes open one: `select(E)`, `sa.select(E)`, `session.get(E, ...)` /
    `get_one`, and the legacy `session.query(E)`. Everything else — a
    relationship load, a refresh, a loader option — begins from a row a scoped
    query already returned.

    `scope.select(E)` is the sanctioned constructor and is exempt. Recognising
    it by the receiver's spelling is a heuristic, and the honest limit of this
    test: it cannot see types, so a `CompanyScope` reached under some third name
    would be flagged, and raw `text("SELECT ...")` is invisible to it entirely.
    """
    match call.func:
        case ast.Name(id="select"):
            return call.args
        case ast.Attribute(attr="select", value=receiver):
            spelling = ast.unparse(receiver)
            if spelling == "scope" or "CompanyScope" in spelling:
                return None
            return call.args
        case ast.Attribute(attr="get" | "get_one" | "query"):
            return call.args[:1]
        case _:
            return None


def _reads_a_scoped_model(call: ast.Call, scoped: set[str]) -> bool:
    arguments = _opens_a_read(call)
    if arguments is None:
        return False
    return any(
        isinstance(node, ast.Name) and node.id in scoped
        for argument in arguments
        for node in ast.walk(argument)
    )


def test_no_read_path_builds_its_own_query_over_a_scoped_entity():
    """The Company filter has to be impossible to forget, not merely easy to remember.

    ADR-0007 gave up the queryset that used to carry this invariant. What
    replaces it is that `CompanyScope.select` is the only query constructor over
    a scoped entity in the whole of `app/` — so a new read path cannot skip the
    Company filter without this test naming the file and line where it did.
    """
    scoped = _scoped_model_names()
    application = Path(__file__).resolve().parent.parent / "app"
    scope_module = application / "core" / "company_scope.py"
    sources = sorted(application.rglob("*.py"))
    offenders: list[str] = []

    for source in sources:
        if source == scope_module:
            continue
        tree = ast.parse(source.read_text())
        offenders += [
            f"{source.relative_to(application.parent)}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _reads_a_scoped_model(node, scoped)
        ]

    assert sources, "scanned nothing, so an empty offender list would mean nothing"
    assert offenders == [], (
        "these read company-scoped rows without going through CompanyScope.select: "
        + ", ".join(offenders)
    )


async def test_a_caller_with_no_company_reaches_nothing(client: AsyncClient):
    """Every read is scoped to a Company, so a caller without one has nowhere to land.

    The refusal happens while the Caller is being built, not at each read: a
    token whose chat claims name no Company never becomes a caller at all.
    """
    _, token = caller_token(company_id=OMITTED)
    headers = bearer(token)
    chat_id = uuid.uuid4()

    responses = [
        await client.get("/auth/me", headers=headers),
        await client.get("/conversations", headers=headers),
        await client.post("/conversations", json={"participant_user_ids": []}, headers=headers),
        await client.get(f"/conversations/{chat_id}/messages", headers=headers),
        await client.post(
            f"/conversations/{chat_id}/messages", json={"body": "oi"}, headers=headers
        ),
    ]

    assert [response.status_code for response in responses] == [401] * len(responses)


async def test_sending_into_another_companys_chat_is_refused(client: AsyncClient):
    company_x = uuid.uuid4()
    company_y = uuid.uuid4()
    _, token_a = caller_token(company_id=company_x)
    user_b_id = uuid.uuid4()
    _, token_b_in_y = caller_token(user_id=user_b_id, company_id=company_y)

    created = await client.post(
        "/conversations",
        json={"participant_user_ids": [str(user_b_id)]},
        headers=bearer(token_a),
    )
    chat_id = created.json()["id"]

    refused = await client.post(
        f"/conversations/{chat_id}/messages",
        json={"body": "de fora"},
        headers=bearer(token_b_in_y),
    )
    never_existed = await client.post(
        f"/conversations/{uuid.uuid4()}/messages",
        json={"body": "de fora"},
        headers=bearer(token_b_in_y),
    )

    assert refused.status_code == 404
    assert (refused.status_code, refused.json()) == (
        never_existed.status_code,
        never_existed.json(),
    )


async def test_websocket_does_not_open_on_another_companys_chat(client: AsyncClient):
    company_x = uuid.uuid4()
    company_y = uuid.uuid4()
    _, token_a = caller_token(company_id=company_x)
    user_b_id = uuid.uuid4()
    _, token_b_in_y = caller_token(user_id=user_b_id, company_id=company_y)

    created = await client.post(
        "/conversations",
        json={"participant_user_ids": [str(user_b_id)]},
        headers=bearer(token_a),
    )
    chat_id = created.json()["id"]

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        with pytest.raises(WebSocketDisconnect) as refusal:
            async with aconnect_ws(
                f"/websocket/conversations/{chat_id}?token={token_b_in_y}", client=ws_client
            ):
                pass
        with pytest.raises(WebSocketDisconnect) as never_existed:
            async with aconnect_ws(
                f"/websocket/conversations/{uuid.uuid4()}?token={token_b_in_y}", client=ws_client
            ):
                pass

    assert refusal.value.code == 1008
    assert refusal.value.code == never_existed.value.code


async def test_user_socket_does_not_receive_another_companys_chat(client: AsyncClient):
    """The live chat-list channel is a read path too, and it is keyed by user alone.

    A user id can exist in two Companies. The Chat summary pushed over
    `/websocket/users/me` carries a Chat id, its name and its participants, so a
    socket opened with one Company's token must never see a Chat from another.
    """
    company_x = uuid.uuid4()
    company_y = uuid.uuid4()
    user_b_id = uuid.uuid4()
    _, token_a_in_x = caller_token(company_id=company_x)
    _, token_c_in_y = caller_token(company_id=company_y)
    _, token_b_in_y = caller_token(user_id=user_b_id, company_id=company_y)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ws_client:
        async with aconnect_ws(
            f"/websocket/users/me?token={token_b_in_y}", client=ws_client
        ) as socket_in_y:
            in_x = await client.post(
                "/conversations",
                json={"participant_user_ids": [str(user_b_id)]},
                headers=bearer(token_a_in_x),
            )
            # B's own Company's traffic follows, so a missing first frame is a
            # boundary holding rather than a dead socket.
            in_y = await client.post(
                "/conversations",
                json={"participant_user_ids": [str(user_b_id)]},
                headers=bearer(token_c_in_y),
            )

            received = await socket_in_y.receive_json(timeout=5)

    assert received["id"] != in_x.json()["id"]
    assert received["id"] == in_y.json()["id"]
