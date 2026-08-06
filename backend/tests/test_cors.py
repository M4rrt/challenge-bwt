from httpx import AsyncClient


async def test_health_allows_configured_frontend_origin(client: AsyncClient):
    response = await client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_health_rejects_other_origins(client: AsyncClient):
    response = await client.get("/health", headers={"Origin": "http://evil.example.com"})

    assert "access-control-allow-origin" not in response.headers
