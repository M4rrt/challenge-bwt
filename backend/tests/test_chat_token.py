import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt

from app.core.chat_token import verify_chat_token
from app.core.config import settings
from tests.chat_tokens import mint_chat_token


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


async def test_me_rejects_a_token_signed_with_another_secret(client: AsyncClient):
    token = mint_chat_token(secret="a-secret-the-service-does-not-hold")

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_rejects_an_expired_token(client: AsyncClient):
    token = mint_chat_token(expires_in=timedelta(minutes=-1))

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_rejects_a_token_carrying_no_chat_claims(client: AsyncClient):
    token = jwt.encode(
        {"sub": str(uuid.uuid4())}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
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
