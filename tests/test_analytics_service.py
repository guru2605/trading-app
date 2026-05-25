"""Tests for AnalyticsService."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.services.analytics import AnalyticsService


@pytest.fixture
def analytics_service(db_session: AsyncSession) -> AnalyticsService:
    return AnalyticsService(db_session)


class TestAnalyticsService:
    async def test_signal_quality_no_data(self, analytics_service: AnalyticsService) -> None:
        result = await analytics_service.signal_quality()
        assert result["available"] is False

    async def test_signal_quality_with_data(
        self, db_session: AsyncSession, analytics_service: AnalyticsService
    ) -> None:
        now = datetime.now(UTC)
        # Add some resolved signals
        for i in range(5):
            sig = Signal(
                tradingsymbol="RELIANCE",
                exchange="NSE",
                signal_type="BUY",
                timeframe="15minute",
                entry_price=2500.0,
                stop_loss=2450.0,
                target_price=2600.0,
                confidence=65.0,
                indicators={},
                rationale="Test",
                status="active",
                outcome="win" if i < 3 else "loss",
                actual_rr=2.0 if i < 3 else -1.0,
                created_at=now - timedelta(days=i),
            )
            db_session.add(sig)
        await db_session.commit()

        result = await analytics_service.signal_quality()
        assert result["available"] is True
        assert result["total_signals"] == 5
        assert result["wins"] == 3
        assert result["losses"] == 2
        assert result["win_rate"] == 60.0

    async def test_performance_by_timeframe_no_data(self, analytics_service: AnalyticsService) -> None:
        result = await analytics_service.performance_by_timeframe()
        assert result["available"] is True
        assert result["breakdown"] == {}

    async def test_performance_by_timeframe_with_data(
        self, db_session: AsyncSession, analytics_service: AnalyticsService
    ) -> None:
        now = datetime.now(UTC)
        for tf, outcome in [("15minute", "win"), ("15minute", "loss"), ("day", "win")]:
            sig = Signal(
                tradingsymbol="INFY",
                exchange="NSE",
                signal_type="BUY",
                timeframe=tf,
                entry_price=1500.0,
                stop_loss=1450.0,
                target_price=1600.0,
                confidence=60.0,
                indicators={},
                rationale="Test",
                status="active",
                outcome=outcome,
                actual_rr=2.0 if outcome == "win" else -1.0,
                created_at=now,
            )
            db_session.add(sig)
        await db_session.commit()

        result = await analytics_service.performance_by_timeframe()
        assert "15minute" in result["breakdown"]
        assert result["breakdown"]["15minute"]["total"] == 2
        assert result["breakdown"]["day"]["total"] == 1

    async def test_performance_by_symbol(self, db_session: AsyncSession, analytics_service: AnalyticsService) -> None:
        now = datetime.now(UTC)
        for sym, outcome in [("RELIANCE", "win"), ("RELIANCE", "win"), ("INFY", "loss")]:
            sig = Signal(
                tradingsymbol=sym,
                exchange="NSE",
                signal_type="BUY",
                timeframe="day",
                entry_price=1000.0,
                stop_loss=950.0,
                target_price=1100.0,
                confidence=55.0,
                indicators={},
                rationale="Test",
                status="active",
                outcome=outcome,
                created_at=now,
            )
            db_session.add(sig)
        await db_session.commit()

        result = await analytics_service.performance_by_symbol()
        assert result["available"] is True
        assert len(result["symbols"]) == 2
        # RELIANCE should be first (100% win rate)
        assert result["symbols"][0]["symbol"] == "RELIANCE"
        assert result["symbols"][0]["win_rate"] == 100.0

    async def test_signal_count_summary(self, db_session: AsyncSession, analytics_service: AnalyticsService) -> None:
        now = datetime.now(UTC)
        for status in ["active", "active", "expired"]:
            sig = Signal(
                tradingsymbol="TCS",
                exchange="NSE",
                signal_type="BUY",
                timeframe="day",
                entry_price=3500.0,
                stop_loss=3400.0,
                target_price=3700.0,
                confidence=50.0,
                indicators={},
                rationale="Test",
                status=status,
                created_at=now,
            )
            db_session.add(sig)
        await db_session.commit()

        result = await analytics_service.signal_count_summary()
        assert result["active"] == 2
        assert result["expired"] == 1
        assert result["total"] == 3
