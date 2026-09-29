import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt

from app.core.chat_token import SUPERVISION_SCOPE, is_supervisor, verify_chat_token
from app.core.config import settings
from tests.chat_tokens import OTHER_KEY_PAIR, TEST_KEY_PAIR, make_caller, mint_chat_token, unsigned_token


async def test_me_returns_the_identity_the_token_carries(client: AsyncClient):
    user_id = uuid.uuid4()
    company_id = uuid.uuid4()
    token = mint_chat_token(
        user_id=user_id,
        company_id=company_id,
        user_kind="staff",
        scopes=["chat:read", "chat:write"],
        display_name="Ana Souza",
        avatar_url="https://cdn.test/ana.png",
    )

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user_id),
        "company_id": str(company_id),
        "user_kind": "staff",
        "scopes": ["chat:read", "chat:write"],
        "display_name": "Ana Souza",
        "avatar_url": "https://cdn.test/ana.png",
    }


async def test_me_rejects_a_missing_token(client: AsyncClient):
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_rejects_a_token_the_service_cannot_verify(client: AsyncClient):
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


async def test_me_rejects_a_token_signed_with_a_key_the_service_does_not_hold(
    client: AsyncClient,
):
    """The same `kid` the service trusts, but a different key behind it.

    Distinct from an unknown `kid`: here the header names a key the service
    *does* recognise, so the rejection has to come from the signature check
    itself, not from a lookup that never finds the key.
    """
    token = mint_chat_token(key_pair=OTHER_KEY_PAIR)

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_rejects_a_token_with_an_unknown_kid(client: AsyncClient):
    token = mint_chat_token(kid="a-kid-the-service-has-never-published")

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_rejects_a_token_declaring_alg_none(client: AsyncClient):
    """The classic algorithm-confusion probe: opt out of a signature entirely.

    A caller who controls their own header must not be able to make the
    service skip verification just by asking for `alg: none`.
    """
    token = unsigned_token(
        {
            "sub": str(uuid.uuid4()),
            "aud": settings.chat_token_audience,
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp(),
            "https://brwinetours.com/chat": {
                "user_kind": "staff",
                "scopes": ["chat:read"],
                "display_name": "Ana Souza",
                "avatar_url": None,
                "company_id": "11111111-1111-1111-1111-111111111111",
            },
        }
    )

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_rejects_a_token_with_no_audience(client: AsyncClient):
    token = mint_chat_token(audience=None)

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_rejects_a_token_with_the_wrong_audience(client: AsyncClient):
    token = mint_chat_token(audience="some-other-product")

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_rejects_an_expired_token(client: AsyncClient):
    token = mint_chat_token(expires_in=timedelta(minutes=-1))

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_rejects_a_token_carrying_no_chat_claims(client: AsyncClient):
    token = mint_chat_token()
    claims = jwt.get_unverified_claims(token)
    del claims["https://brwinetours.com/chat"]
    token = jwt.encode(
        claims,
        TEST_KEY_PAIR.private_pem,
        algorithm="RS256",
        headers={"kid": TEST_KEY_PAIR.kid},
    )

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/auth/register"),
        ("POST", "/auth/login"),
        ("POST", "/auth/refresh"),
        ("POST", "/auth/logout"),
        ("GET", "/users"),
    ],
)
async def test_the_service_has_no_login_of_its_own(client: AsyncClient, method: str, path: str):
    response = await client.request(method, path, json={})

    assert response.status_code == 404


def test_a_verified_token_carries_the_moment_it_expires():
    """The socket needs the deadline, and the only place it can come from is the token.

    ADR-0011 makes the fifteen-minute lifetime the revocation mechanism, so
    "when does this expire" stops being the JWT library's private business and
    becomes something the service schedules against.
    """
    expires_in = timedelta(minutes=15)
    before = datetime.now(timezone.utc)

    caller = verify_chat_token(mint_chat_token(expires_in=expires_in))

    assert caller is not None
    assert before + expires_in - timedelta(seconds=5) <= caller.expires_at
    assert caller.expires_at <= datetime.now(timezone.utc) + expires_in


def test_a_token_that_never_expires_is_not_a_chat_token():
    """No expiry means no revocation, which is the whole of ADR-0011.

    The library only checks an `exp` it finds, so a token issued without one is
    accepted forever by default. Here that is a token the service refuses
    rather than a token the service cannot take away.
    """
    assert verify_chat_token(mint_chat_token(expires_in=None)) is None


def test_a_caller_carrying_the_supervision_scope_is_a_supervisor():
    """Supervision travels as a scope, per ADR-0009 — not as a third user kind.

    Ticket 13's own note: `may_read` classifies a reader by
    `ParticipantRole(reader_kind)`, whose members are exactly `staff | client`.
    Reusing that predicate for a Supervisor — instead of opening a bypass for
    them — only works if the Supervisor's token still carries an ordinary
    `user_kind` and adds supervision on top of it as a scope.
    """
    caller = make_caller(scopes=("chat:read", "chat:write", SUPERVISION_SCOPE))

    assert is_supervisor(caller) is True


def test_a_caller_without_the_supervision_scope_is_not_a_supervisor():
    caller = make_caller(scopes=("chat:read", "chat:write"))

    assert is_supervisor(caller) is False
