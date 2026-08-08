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


async def test_list_conversations_includes_null_last_message_at_when_no_messages(
    client: AsyncClient,
):
    user_a_id, headers_a = await _register_and_login(client, "quim@example.com")
    user_b_id, _ = await _register_and_login(client, "rita@example.com")

    await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )

    response = await client.get("/conversations", headers=headers_a)

    assert response.status_code == 200
    assert response.json()[0]["last_message_at"] is None


async def test_list_conversations_reflects_most_recent_message_timestamp(
    client: AsyncClient,
):
    user_a_id, headers_a = await _register_and_login(client, "sonia@example.com")
    user_b_id, _ = await _register_and_login(client, "tulio@example.com")

    create_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )
    conversation_id = create_response.json()["id"]

    send_response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"body": "oi"},
        headers=headers_a,
    )
    message_created_at = send_response.json()["created_at"]

    response = await client.get("/conversations", headers=headers_a)

    assert response.status_code == 200
    assert response.json()[0]["last_message_at"] == message_created_at


async def test_list_conversations_orders_by_most_recent_message_first(client: AsyncClient):
    user_a_id, headers_a = await _register_and_login(client, "urso@example.com")
    user_b_id, _ = await _register_and_login(client, "vitoria@example.com")
    user_c_id, _ = await _register_and_login(client, "wagner@example.com")

    older_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id]},
        headers=headers_a,
    )
    older_id = older_response.json()["id"]
    await client.post(
        f"/conversations/{older_id}/messages",
        json={"body": "mensagem antiga"},
        headers=headers_a,
    )

    no_messages_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_c_id], "name": "Sem mensagens"},
        headers=headers_a,
    )
    no_messages_id = no_messages_response.json()["id"]

    newer_response = await client.post(
        "/conversations",
        json={"participant_user_ids": [user_b_id, user_c_id], "name": "Recente"},
        headers=headers_a,
    )
    newer_id = newer_response.json()["id"]
    await client.post(
        f"/conversations/{newer_id}/messages",
        json={"body": "mensagem recente"},
        headers=headers_a,
    )

    response = await client.get("/conversations", headers=headers_a)

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [newer_id, older_id, no_messages_id]


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
