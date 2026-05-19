from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient


async def test_login_redirects(client: AsyncClient) -> None:
    with patch("app.routers.auth.get_login_url", return_value="https://kite.zerodha.com/connect/login?api_key=test"):
        response = await client.get("/api/auth/login", follow_redirects=False)
        assert response.status_code == 307
        assert "kite.zerodha.com" in response.headers["location"]


async def test_callback_success(client: AsyncClient) -> None:
    with patch("app.routers.auth.handle_callback", new_callable=AsyncMock) as mock_handle:
        mock_handle.return_value = "test_access_token_12345"
        response = await client.get("/api/auth/callback", params={"request_token": "test_request_token"})
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        mock_handle.assert_called_once()


async def test_callback_failure(client: AsyncClient) -> None:
    with patch("app.routers.auth.handle_callback", new_callable=AsyncMock) as mock_handle:
        mock_handle.side_effect = Exception("Invalid request token")
        response = await client.get("/api/auth/callback", params={"request_token": "bad_token"})
        assert response.status_code == 400


async def test_auth_status_not_authenticated(client: AsyncClient, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = None
    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False


async def test_auth_status_authenticated(client: AsyncClient, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = "some_token"
    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


async def test_handle_callback_stores_token() -> None:
    mock_redis = AsyncMock()
    mock_kite = MagicMock()
    mock_kite.generate_session.return_value = {"access_token": "abc123"}

    with patch("app.kite.auth.KiteConnect", return_value=mock_kite):
        from app.kite.auth import handle_callback

        token = await handle_callback("req_token", mock_redis)
        assert token == "abc123"
        mock_redis.set.assert_called_once_with("kite:access_token", "abc123", ex=86400)


async def test_get_stored_access_token_returns_string() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.return_value = "stored_token"

    from app.kite.auth import get_stored_access_token

    token = await get_stored_access_token(mock_redis)
    assert token == "stored_token"


async def test_get_stored_access_token_returns_none() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None

    from app.kite.auth import get_stored_access_token

    token = await get_stored_access_token(mock_redis)
    assert token is None
