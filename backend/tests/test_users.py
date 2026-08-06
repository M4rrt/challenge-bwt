from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> tuple[str, dict[str, str]]:
    username = email.split("@")[0]
    register_response = await client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": "Senha-Forte-123"},
    )
    user_id = register_response.json()["id"]

    login_response = await client.post(
        "/auth/login", json={"email": email, "password": "Senha-Forte-123"}
    )
    token = login_response.json()["access_token"]

    return user_id, {"Authorization": f"Bearer {token}"}


async def test_list_users_returns_all_registered_users(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "users-a@example.com")
    user_b_id, _ = await _register_and_login(client, "users-b@example.com")

    response = await client.get("/users", headers=headers_a)

    assert response.status_code == 200
    body = response.json()
    ids = {user["id"] for user in body}
    assert {user_a_id, user_b_id}.issubset(ids)
    matched = next(user for user in body if user["id"] == user_a_id)
    assert matched["username"] == "users-a"
    assert "email" not in matched
    assert "hashed_password" not in matched


async def test_list_users_rejects_unauthenticated(client: AsyncClient):
    response = await client.get("/users")

    assert response.status_code == 401
