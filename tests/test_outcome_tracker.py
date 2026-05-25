from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.tasks.outcome_tracker import evaluate_signal_outcomes


@pytest.fixture
def market_data() -> AsyncMock:
    return AsyncMock()


class TestOutcomeTracker:
    async def test_buy_win(self, db_session: AsyncSession, market_data: AsyncMock) -> None:
        signal = Signal(
            tradingsymbol="RELIANCE",
            exchange="NSE",
            signal_type="BUY",
            timeframe="15minute",
            entry_price=2500.0,
            stop_loss=2460.0,
            target_price=2580.0,
            confidence=65.0,
            indicators={},
            rationale="Test",
            status="active",
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)

        market_data.fetch_historical.return_value = [
            {"date": datetime.now(UTC), "open": 2550.0, "high": 2590.0, "low": 2540.0, "close": 2585.0, "volume": 1000}
        ]

        resolved = await evaluate_signal_outcomes(db_session, market_data)
        assert resolved == 1

        await db_session.refresh(signal)
        assert signal.outcome == "win"
        assert signal.actual_exit_price == 2580.0
        assert signal.actual_rr is not None
        assert signal.actual_rr > 0

    async def test_buy_loss(self, db_session: AsyncSession, market_data: AsyncMock) -> None:
        signal = Signal(
            tradingsymbol="TCS",
            exchange="NSE",
            signal_type="BUY",
            timeframe="15minute",
            entry_price=3500.0,
            stop_loss=3450.0,
            target_price=3600.0,
            confidence=60.0,
            indicators={},
            rationale="Test",
            status="active",
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)

        market_data.fetch_historical.return_value = [
            {"date": datetime.now(UTC), "open": 3480.0, "high": 3490.0, "low": 3440.0, "close": 3445.0, "volume": 1000}
        ]

        resolved = await evaluate_signal_outcomes(db_session, market_data)
        assert resolved == 1

        await db_session.refresh(signal)
        assert signal.outcome == "loss"
        assert signal.status == "expired"
        assert signal.actual_rr is not None
        assert signal.actual_rr < 0

    async def test_sell_win(self, db_session: AsyncSession, market_data: AsyncMock) -> None:
        signal = Signal(
            tradingsymbol="INFY",
            exchange="NSE",
            signal_type="SELL",
            timeframe="15minute",
            entry_price=1500.0,
            stop_loss=1540.0,
            target_price=1420.0,
            confidence=55.0,
            indicators={},
            rationale="Test",
            status="active",
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)

        market_data.fetch_historical.return_value = [
            {"date": datetime.now(UTC), "open": 1450.0, "high": 1460.0, "low": 1410.0, "close": 1415.0, "volume": 1000}
        ]

        resolved = await evaluate_signal_outcomes(db_session, market_data)
        assert resolved == 1

        await db_session.refresh(signal)
        assert signal.outcome == "win"

    async def test_no_outcome_yet(self, db_session: AsyncSession, market_data: AsyncMock) -> None:
        signal = Signal(
            tradingsymbol="HDFCBANK",
            exchange="NSE",
            signal_type="BUY",
            timeframe="15minute",
            entry_price=1600.0,
            stop_loss=1560.0,
            target_price=1680.0,
            confidence=50.0,
            indicators={},
            rationale="Test",
            status="active",
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)

        # Price between SL and target — no outcome
        market_data.fetch_historical.return_value = [
            {"date": datetime.now(UTC), "open": 1610.0, "high": 1620.0, "low": 1590.0, "close": 1615.0, "volume": 1000}
        ]

        resolved = await evaluate_signal_outcomes(db_session, market_data)
        assert resolved == 0

        await db_session.refresh(signal)
        assert signal.outcome is None

    async def test_auto_expire(self, db_session: AsyncSession, market_data: AsyncMock) -> None:
        signal = Signal(
            tradingsymbol="WIPRO",
            exchange="NSE",
            signal_type="BUY",
            timeframe="15minute",
            entry_price=400.0,
            stop_loss=390.0,
            target_price=420.0,
            confidence=50.0,
            indicators={},
            rationale="Test",
            status="active",
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)

        # Backdate the signal to 11 days ago
        signal.created_at = datetime.now(UTC) - timedelta(days=11)
        await db_session.commit()

        market_data.fetch_historical.return_value = [
            {"date": datetime.now(UTC), "open": 405.0, "high": 410.0, "low": 395.0, "close": 405.0, "volume": 1000}
        ]

        resolved = await evaluate_signal_outcomes(db_session, market_data)
        assert resolved == 1

        await db_session.refresh(signal)
        assert signal.outcome == "expired"
        assert signal.status == "expired"

    async def test_empty_signals(self, db_session: AsyncSession, market_data: AsyncMock) -> None:
        resolved = await evaluate_signal_outcomes(db_session, market_data)
        assert resolved == 0

    async def test_already_resolved_skipped(self, db_session: AsyncSession, market_data: AsyncMock) -> None:
        signal = Signal(
            tradingsymbol="RELIANCE",
            exchange="NSE",
            signal_type="BUY",
            timeframe="15minute",
            entry_price=2500.0,
            stop_loss=2460.0,
            target_price=2580.0,
            confidence=65.0,
            indicators={},
            rationale="Test",
            status="active",
            outcome="win",
        )
        db_session.add(signal)
        await db_session.commit()

        resolved = await evaluate_signal_outcomes(db_session, market_data)
        assert resolved == 0
