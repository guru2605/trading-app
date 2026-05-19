from httpx import AsyncClient


async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/_status")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "kite-trader"
    assert data["status"] == "ok"
