import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from jose import jwt

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
