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


async def test_create_one_to_one_conversation(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "ana@example.com")
    user_b_id, _ = await _register_and_login(client, "beto@example.com")

    response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] is None
    assert set(body["participant_user_ids"]) == {user_a_id, user_b_id}


async def test_create_group_conversation(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "carla@example.com")
    user_b_id, _ = await _register_and_login(client, "davi@example.com")
    user_c_id, _ = await _register_and_login(client, "elis@example.com")

    response = await client.post(
        "/conversations",
        json={
            "participant_user_ids": [user_b_id, user_c_id],
            "name": "Trio",
        },
        headers=headers_a,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Trio"
    assert set(body["participant_user_ids"]) == {user_a_id, user_b_id, user_c_id}


async def test_create_group_conversation_requires_name(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "fabio@example.com")
    user_b_id, _ = await _register_and_login(client, "gina@example.com")
    user_c_id, _ = await _register_and_login(client, "hugo@example.com")

    response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id, user_c_id]},
        headers=headers_a,
    )

    assert response.status_code == 422


async def test_duplicate_one_to_one_creation_returns_existing_conversation(
    client: AsyncClient,
):
    user_a_id, headers_a = await _register_and_login(client, "ivo@example.com")
    user_b_id, _ = await _register_and_login(client, "julia@example.com")

    first_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )
    second_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["id"] == second_response.json()["id"]


async def test_one_to_one_creation_ignores_group_with_same_two_members(
    client: AsyncClient,
):
    user_a_id, headers_a = await _register_and_login(client, "karen@example.com")
    user_b_id, _ = await _register_and_login(client, "leo@example.com")
    user_c_id, _ = await _register_and_login(client, "mara@example.com")

    group_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id, user_c_id], "name": "Trio 2"},
        headers=headers_a,
    )
    one_to_one_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )

    assert group_response.json()["id"] != one_to_one_response.json()["id"]
    assert set(one_to_one_response.json()["participant_user_ids"]) == {
        user_a_id,
        user_b_id,
    }


async def test_list_conversations_returns_only_own_conversations(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "nina@example.com")
    user_b_id, headers_b = await _register_and_login(client, "otto@example.com")
    _, headers_c = await _register_and_login(client, "paula@example.com")

    shared_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )
    shared_conversation_id = shared_response.json()["id"]

    await client.post(
        "/conversations",
        json={"participant_user_ids": [user_a_id]},
        headers=headers_c,
    )

    response = await client.get("/conversations", headers=headers_b)

    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body] == [shared_conversation_id]
