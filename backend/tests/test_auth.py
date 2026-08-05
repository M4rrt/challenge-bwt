from httpx import AsyncClient
from jose import jwt

from app.core.config import settings


async def test_register_creates_user(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": "ana@example.com", "password": "senha-forte-123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ana@example.com"
    assert "password" not in body
    assert "id" in body


async def test_register_rejects_duplicate_email(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "senha-forte-123"},
    )

    response = await client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "outra-senha-456"},
    )

    assert response.status_code == 409


async def test_login_issues_valid_jwt(client: AsyncClient):
    register_response = await client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "senha-forte-123"},
    )
    user_id = register_response.json()["id"]

    response = await client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "senha-forte-123"},
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == user_id


async def test_me_rejects_missing_token(client: AsyncClient):
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_rejects_invalid_token(client: AsyncClient):
    response = await client.get(
        "/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
