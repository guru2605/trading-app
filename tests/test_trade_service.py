from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade
from app.services.trade import TradeService


@pytest.fixture
def mock_kite() -> AsyncMock:
    return AsyncMock()


async def test_sync_trades_inserts_new(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    mock_kite.trades.return_value = [
        {
            "order_id": "ORD001",
            "exchange_order_id": "EXC001",
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 1500.0,
            "product": "CNC",
            "order_type": "MARKET",
            "status": "COMPLETE",
            "fill_timestamp": None,
        },
        {
            "order_id": "ORD002",
            "exchange_order_id": "EXC002",
            "tradingsymbol": "TCS",
            "exchange": "NSE",
            "transaction_type": "SELL",
            "quantity": 5,
            "price": 3500.0,
            "product": "CNC",
            "order_type": "LIMIT",
            "status": "COMPLETE",
            "fill_timestamp": None,
        },
    ]

    service = TradeService(db_session, mock_kite)
    count = await service.sync_trades()

    assert count == 2
    trades = await service.get_trades()
    assert len(trades) == 2


async def test_sync_trades_dedup(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    # Pre-populate a trade
    db_session.add(
        Trade(
            order_id="ORD001",
            tradingsymbol="INFY",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            price=1500.0,
            product="CNC",
            order_type="MARKET",
        )
    )
    await db_session.commit()

    mock_kite.trades.return_value = [
        {
            "order_id": "ORD001",
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 1500.0,
            "product": "CNC",
            "order_type": "MARKET",
            "status": "COMPLETE",
        },
        {
            "order_id": "ORD003",
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 2,
            "price": 2500.0,
            "product": "CNC",
            "order_type": "MARKET",
            "status": "COMPLETE",
        },
    ]

    service = TradeService(db_session, mock_kite)
    count = await service.sync_trades()

    # Only ORD003 should be inserted (ORD001 already exists)
    assert count == 1
    trades = await service.get_trades()
    assert len(trades) == 2


async def test_get_trades_filter_by_symbol(db_session: AsyncSession) -> None:
    db_session.add(
        Trade(
            order_id="ORD001",
            tradingsymbol="INFY",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            price=1500.0,
            product="CNC",
            order_type="MARKET",
        )
    )
    db_session.add(
        Trade(
            order_id="ORD002",
            tradingsymbol="TCS",
            exchange="NSE",
            transaction_type="BUY",
            quantity=5,
            price=3500.0,
            product="CNC",
            order_type="MARKET",
        )
    )
    await db_session.commit()

    service = TradeService(db_session)
    trades = await service.get_trades(tradingsymbol="INFY")
    assert len(trades) == 1
    assert trades[0].tradingsymbol == "INFY"


async def test_get_trades_filter_by_transaction_type(db_session: AsyncSession) -> None:
    db_session.add(
        Trade(
            order_id="ORD001",
            tradingsymbol="INFY",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            price=1500.0,
            product="CNC",
            order_type="MARKET",
        )
    )
    db_session.add(
        Trade(
            order_id="ORD002",
            tradingsymbol="TCS",
            exchange="NSE",
            transaction_type="SELL",
            quantity=5,
            price=3500.0,
            product="CNC",
            order_type="MARKET",
        )
    )
    await db_session.commit()

    service = TradeService(db_session)
    trades = await service.get_trades(transaction_type="SELL")
    assert len(trades) == 1
    assert trades[0].transaction_type == "SELL"


async def test_get_trades_respects_limit(db_session: AsyncSession) -> None:
    for i in range(5):
        db_session.add(
            Trade(
                order_id=f"ORD{i:03d}",
                tradingsymbol="INFY",
                exchange="NSE",
                transaction_type="BUY",
                quantity=1,
                price=100.0,
                product="CNC",
                order_type="MARKET",
            )
        )
    await db_session.commit()

    service = TradeService(db_session)
    trades = await service.get_trades(limit=3)
    assert len(trades) == 3


async def test_sync_trades_requires_kite(db_session: AsyncSession) -> None:
    service = TradeService(db_session)
    with pytest.raises(RuntimeError, match="Kite client required"):
        await service.sync_trades()
