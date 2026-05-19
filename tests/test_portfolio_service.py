from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.sector_map import SectorMap
from app.services.portfolio import PortfolioService


@pytest.fixture
def mock_kite() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def portfolio_service(db_session: AsyncSession, mock_kite: AsyncMock) -> PortfolioService:
    return PortfolioService(db_session, mock_kite)


async def test_sync_holdings_inserts_new(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    mock_kite.holdings.return_value = [
        {
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "isin": "INE009A01021",
            "quantity": 10,
            "average_price": 1500.0,
            "last_price": 1550.0,
            "pnl": 500.0,
            "day_change": 20.0,
            "day_change_percentage": 1.31,
        },
        {
            "tradingsymbol": "TCS",
            "exchange": "NSE",
            "isin": "INE467B01029",
            "quantity": 5,
            "average_price": 3500.0,
            "last_price": 3600.0,
            "pnl": 500.0,
            "day_change": 50.0,
            "day_change_percentage": 1.41,
        },
    ]

    service = PortfolioService(db_session, mock_kite)
    count = await service.sync_holdings()

    assert count == 2
    holdings = await service.get_holdings()
    assert len(holdings) == 2
    symbols = {h.tradingsymbol for h in holdings}
    assert symbols == {"INFY", "TCS"}


async def test_sync_holdings_upserts_existing(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    # Pre-populate a holding
    holding = Holding(
        tradingsymbol="INFY",
        exchange="NSE",
        isin="INE009A01021",
        quantity=5,
        average_price=1400.0,
        last_price=1450.0,
        pnl=250.0,
    )
    db_session.add(holding)
    await db_session.commit()

    mock_kite.holdings.return_value = [
        {
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "isin": "INE009A01021",
            "quantity": 10,
            "average_price": 1500.0,
            "last_price": 1550.0,
            "pnl": 500.0,
            "day_change": 20.0,
            "day_change_percentage": 1.31,
        },
    ]

    service = PortfolioService(db_session, mock_kite)
    count = await service.sync_holdings()

    assert count == 1
    holdings = await service.get_holdings()
    assert len(holdings) == 1
    assert holdings[0].quantity == 10
    assert holdings[0].average_price == 1500.0


async def test_sync_holdings_zeros_exited(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    # Pre-populate holdings
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1550.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=5, average_price=3500.0, last_price=3600.0))
    await db_session.commit()

    # Only INFY returned from Kite (TCS exited)
    mock_kite.holdings.return_value = [
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

    service = PortfolioService(db_session, mock_kite)
    await service.sync_holdings()

    # Only INFY should appear (TCS zeroed out)
    holdings = await service.get_holdings()
    assert len(holdings) == 1
    assert holdings[0].tradingsymbol == "INFY"


async def test_get_summary(portfolio_service: PortfolioService, db_session: AsyncSession) -> None:
    db_session.add(
        Holding(
            tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0, day_change=10.0
        )
    )
    db_session.add(
        Holding(
            tradingsymbol="TCS", exchange="NSE", quantity=5, average_price=3500.0, last_price=3400.0, day_change=-20.0
        )
    )
    await db_session.commit()

    summary = await portfolio_service.get_summary()

    assert summary.holdings_count == 2
    assert summary.total_invested == 32500.0  # 15000 + 17500
    assert summary.total_current == 33000.0  # 16000 + 17000
    assert summary.total_pnl == 500.0
    assert summary.day_pnl == 0.0  # (10*10) + (5*-20) = 100 - 100 = 0


async def test_get_allocation(portfolio_service: PortfolioService, db_session: AsyncSession) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=5, average_price=3500.0, last_price=3400.0))
    db_session.add(SectorMap(tradingsymbol="INFY", sector="IT"))
    db_session.add(SectorMap(tradingsymbol="TCS", sector="IT"))
    await db_session.commit()

    allocation = await portfolio_service.get_allocation()

    assert allocation.total_value == 33000.0  # 16000 + 17000
    assert len(allocation.allocations) == 1
    assert allocation.allocations[0].sector == "IT"
    assert allocation.allocations[0].holdings_count == 2
    assert allocation.allocations[0].weight == 100.0


async def test_get_allocation_unknown_sector(portfolio_service: PortfolioService, db_session: AsyncSession) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    await db_session.commit()

    allocation = await portfolio_service.get_allocation()

    assert len(allocation.allocations) == 1
    assert allocation.allocations[0].sector == "Unknown"


async def test_get_holdings_weight(portfolio_service: PortfolioService, db_session: AsyncSession) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1000.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=10, average_price=3500.0, last_price=3000.0))
    await db_session.commit()

    holdings = await portfolio_service.get_holdings()

    assert len(holdings) == 2
    weights = {h.tradingsymbol: h.weight for h in holdings}
    assert weights["INFY"] == 25.0  # 10000/40000
    assert weights["TCS"] == 75.0  # 30000/40000
