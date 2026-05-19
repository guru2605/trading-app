from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.deps import get_db, get_kite_client, get_redis
from app.kite.client import KiteClient
from app.main import app
from app.models.holding import Holding

from .conftest import test_async_session, test_engine


@pytest.fixture
async def setup_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_async_session() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_kite_client() -> AsyncMock:
    mock = AsyncMock(spec=KiteClient)
    mock.positions.return_value = {"net": [], "day": []}
    mock.orders.return_value = []
    mock.holdings.return_value = []
    return mock


@pytest.fixture
async def api_client(setup_db: AsyncSession, mock_kite_client: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_async_session() as session:
            yield session

    async def override_get_redis() -> AsyncMock:
        return AsyncMock()

    async def override_get_kite_client() -> AsyncMock:
        return mock_kite_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_kite_client] = override_get_kite_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def test_get_holdings_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/portfolio/holdings")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_holdings_with_data(api_client: AsyncClient, setup_db: AsyncSession) -> None:
    setup_db.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    await setup_db.commit()

    resp = await api_client.get("/api/portfolio/holdings")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["tradingsymbol"] == "INFY"
    assert data[0]["weight"] == 100.0


async def test_get_positions(api_client: AsyncClient, mock_kite_client: AsyncMock) -> None:
    mock_kite_client.positions.return_value = {
        "net": [
            {
                "tradingsymbol": "INFY",
                "exchange": "NSE",
                "product": "CNC",
                "quantity": 10,
                "average_price": 1500.0,
                "last_price": 1550.0,
                "pnl": 500.0,
            }
        ],
        "day": [],
    }

    resp = await api_client.get("/api/portfolio/positions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["tradingsymbol"] == "INFY"


async def test_get_orders(api_client: AsyncClient, mock_kite_client: AsyncMock) -> None:
    mock_kite_client.orders.return_value = [
        {
            "order_id": "123",
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "product": "CNC",
            "quantity": 10,
            "price": 1500.0,
            "status": "COMPLETE",
            "filled_quantity": 10,
            "average_price": 1500.0,
        }
    ]

    resp = await api_client.get("/api/portfolio/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["order_id"] == "123"


async def test_get_summary_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/portfolio/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["holdings_count"] == 0
    assert data["total_invested"] == 0.0


async def test_get_summary_with_holdings(api_client: AsyncClient, setup_db: AsyncSession) -> None:
    setup_db.add(
        Holding(
            tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0, day_change=10.0
        )
    )
    await setup_db.commit()

    resp = await api_client.get("/api/portfolio/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["holdings_count"] == 1
    assert data["total_invested"] == 15000.0
    assert data["total_current"] == 16000.0
    assert data["total_pnl"] == 1000.0


async def test_get_allocation_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/portfolio/allocation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["allocations"] == []
    assert data["total_value"] == 0.0


async def test_get_exposure(api_client: AsyncClient, setup_db: AsyncSession, mock_kite_client: AsyncMock) -> None:
    setup_db.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    await setup_db.commit()

    mock_kite_client.positions.return_value = {"net": [], "day": []}

    resp = await api_client.get("/api/portfolio/exposure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["long_exposure"] == 16000.0
    assert data["short_exposure"] == 0.0
    assert data["directional_bias"] == "long"


async def test_sync_holdings(api_client: AsyncClient, mock_kite_client: AsyncMock) -> None:
    mock_kite_client.holdings.return_value = [
        {
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "quantity": 10,
            "average_price": 1500.0,
            "last_price": 1550.0,
            "pnl": 500.0,
            "day_change": 0.0,
            "day_change_percentage": 0.0,
        },
    ]

    resp = await api_client.post("/api/portfolio/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert data["synced"] == 1
    assert "Synced 1 holdings" in data["message"]
