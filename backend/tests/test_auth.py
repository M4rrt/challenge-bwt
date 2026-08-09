from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.auth import hash_password, hash_refresh_token


async def test_register_creates_user(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": "ana@example.com", "username": "ana", "password": "Senha-Forte-123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ana@example.com"
    assert body["username"] == "ana"
    assert "password" not in body
    assert "id" in body


async def test_register_requires_username(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": "sem-username@example.com", "password": "Senha-Forte-123"},
    )

    assert response.status_code == 422


async def test_register_rejects_duplicate_email(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "dup@example.com", "username": "dup1", "password": "Senha-Forte-123"},
    )

    response = await client.post(
        "/auth/register",
        json={"email": "dup@example.com", "username": "dup2", "password": "Outra-Senha-456"},
    )

    assert response.status_code == 409


async def test_register_rejects_duplicate_username(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "dupuser1@example.com", "username": "dupuser", "password": "Senha-Forte-123"},
    )

    response = await client.post(
        "/auth/register",
        json={"email": "dupuser2@example.com", "username": "dupuser", "password": "Outra-Senha-456"},
    )

    assert response.status_code == 409


async def test_login_issues_valid_jwt(client: AsyncClient):
    register_response = await client.post(
        "/auth/register",
        json={"email": "login@example.com", "username": "login", "password": "Senha-Forte-123"},
    )
    user_id = register_response.json()["id"]

    response = await client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "Senha-Forte-123"},
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


async def test_register_rejects_invalid_email(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "username": "invalido", "password": "Senha-Forte-123"},
    )

    assert response.status_code == 422


async def test_register_rejects_weak_password(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": "fraca@example.com", "username": "fraca", "password": "senha-fraca"},
    )

    assert response.status_code == 422


async def test_login_rejects_invalid_email(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "whatever"},
    )

    assert response.status_code == 422


async def test_login_accepts_valid_email_with_legacy_weak_password(
    client: AsyncClient, db_session: AsyncSession
):
    legacy_user = User(
        email="legado@example.com", username="legado", hashed_password=hash_password("fraca")
    )
    db_session.add(legacy_user)
    await db_session.commit()

    response = await client.post(
        "/auth/login",
        json={"email": "legado@example.com", "password": "fraca"},
    )

    assert response.status_code == 200


async def test_login_returns_refresh_token(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "refresh@example.com", "username": "refresh", "password": "Senha-Forte-123"},
    )

    response = await client.post(
        "/auth/login",
        json={"email": "refresh@example.com", "password": "Senha-Forte-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["refresh_token"], str)
    assert body["refresh_token"] != ""


async def test_refresh_issues_new_access_token(client: AsyncClient):
    register_response = await client.post(
        "/auth/register",
        json={"email": "renova@example.com", "username": "renova", "password": "Senha-Forte-123"},
    )
    user_id = register_response.json()["id"]
    login_response = await client.post(
        "/auth/login",
        json={"email": "renova@example.com", "password": "Senha-Forte-123"},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    new_access_token = response.json()["access_token"]
    payload = jwt.decode(new_access_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == user_id


async def test_refresh_rejects_invalid_token(client: AsyncClient):
    response = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-refresh-token"})

    assert response.status_code == 401


async def test_refresh_rejects_missing_token(client: AsyncClient):
    response = await client.post("/auth/refresh", json={})

    assert response.status_code == 401


async def test_refresh_rejects_expired_token(client: AsyncClient, db_session: AsyncSession):
    user = User(
        email="expirado@example.com", username="expirado", hashed_password=hash_password("Senha-Forte-123")
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    raw_token = "expired-raw-token"
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db_session.commit()

    response = await client.post("/auth/refresh", json={"refresh_token": raw_token})

    assert response.status_code == 401


async def test_refresh_rejects_revoked_token(client: AsyncClient, db_session: AsyncSession):
    user = User(
        email="revogado@example.com", username="revogado", hashed_password=hash_password("Senha-Forte-123")
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    raw_token = "revoked-raw-token"
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            revoked_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    response = await client.post("/auth/refresh", json={"refresh_token": raw_token})

    assert response.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "logout@example.com", "username": "logout", "password": "Senha-Forte-123"},
    )
    login_response = await client.post(
        "/auth/login",
        json={"email": "logout@example.com", "password": "Senha-Forte-123"},
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_response.status_code == 204

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 401


async def test_logout_is_a_no_op_for_unknown_token(client: AsyncClient):
    response = await client.post("/auth/logout", json={"refresh_token": "never-issued"})

    assert response.status_code == 204
