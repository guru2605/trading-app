from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.models.watchlist_item import WatchlistItem
from app.services.scanner import ScannerService, SignalScoringConfig


def _make_candles(n: int = 100, base: float = 100.0) -> list[dict[str, Any]]:
    """Generate synthetic candle data as list of dicts (Kite format)."""
    rng = np.random.default_rng(42)
    candles = []
    price = base
    for i in range(n):
        change = rng.normal(0, 1.0)
        price = max(price + change, 1.0)
        candles.append(
            {
                "date": datetime(2024, 1, 1) + timedelta(minutes=15 * i),
                "open": round(price + rng.uniform(-0.5, 0.5), 2),
                "high": round(price + rng.uniform(0.5, 2.0), 2),
                "low": round(max(price - rng.uniform(0.5, 2.0), 0.1), 2),
                "close": round(price, 2),
                "volume": int(rng.integers(100000, 1000000)),
            }
        )
    return candles


@pytest.fixture
def scanner_service(db_session: AsyncSession) -> ScannerService:
    return ScannerService(db_session)


class TestScannerServiceScoring:
    def test_score_buy_all_bullish(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": True},
            "macd": {"bullish_crossover": True, "histogram_positive": True},
            "ema": {"bullish_crossover": True, "bullish_trend": True},
            "vwap": {"price_above_vwap": True},
            "bollinger": {"near_lower": True},
            "volume": {"spike": True},
            "support_resistance": {"near_support": True, "near_resistance": True},
            "week_52": {"near_low": True},
            "adx": {"strong_trend": True, "bullish_di": True},
            "stoch_rsi": {"oversold": True, "bullish_crossover": True},
            "candlestick": {"hammer": True, "bullish_engulfing": True},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 20+10, MACD: 20+10, EMA: 15, VWAP: 10, BB: 15, Vol: 10, SR: 15, Breakout: 20, 52w: 5
        # ADX: 15, Stoch: 10+10, Candle: 10+15 = 210
        assert score == 210

    def test_score_buy_no_signals(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": False, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "adx": {"strong_trend": False, "bullish_di": False},
            "stoch_rsi": {"oversold": False, "bullish_crossover": False},
            "candlestick": {"hammer": False, "bullish_engulfing": False},
        }
        score = ScannerService._score_buy(indicators)
        assert score == 0

    def test_score_sell_all_bearish(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"overbought": True, "dropping_from_overbought": True},
            "macd": {"bearish_crossover": True, "histogram_positive": False},
            "ema": {"bearish_crossover": True, "bearish_trend": True},
            "vwap": {"price_below_vwap": True},
            "bollinger": {"near_upper": True},
            "volume": {"spike": True},
            "support_resistance": {"near_resistance": True, "near_support": True},
            "week_52": {"near_high": True},
            "adx": {"strong_trend": True, "bearish_di": True},
            "stoch_rsi": {"overbought": True, "bearish_crossover": True},
            "candlestick": {"inverted_hammer": True, "bearish_engulfing": True},
        }
        score = ScannerService._score_sell(indicators)
        # RSI: 20+10, MACD: 20+10, EMA: 15, VWAP: 10, BB: 15, Vol: 10, SR: 15, Breakdown: 20, 52w: 5
        # ADX: 15, Stoch: 10+10, Candle: 10+15 = 210
        assert score == 210

    def test_score_buy_partial(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": True},
            "ema": {"bullish_crossover": False, "bullish_trend": True},
            "vwap": {"price_above_vwap": True},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 20, MACD: 10, EMA: 5, VWAP: 10 = 45
        assert score == 45


class TestScannerServiceSLTarget:
    def test_buy_sl_target_basic(self) -> None:
        config = SignalScoringConfig()
        service = ScannerService.__new__(ScannerService)
        service.scoring_config = config

        sl = service._compute_stop_loss(100.0, 2.0, "BUY", {})
        assert sl == 100.0 - 2.0 * 1.5  # 97.0

        target = service._compute_target(100.0, sl, "BUY")
        risk = 100.0 - sl
        assert target == 100.0 + risk * 2.0  # 106.0

    def test_sell_sl_target_basic(self) -> None:
        config = SignalScoringConfig()
        service = ScannerService.__new__(ScannerService)
        service.scoring_config = config

        sl = service._compute_stop_loss(100.0, 2.0, "SELL", {})
        assert sl == 100.0 + 2.0 * 1.5  # 103.0

        target = service._compute_target(100.0, sl, "SELL")
        risk = sl - 100.0
        assert target == 100.0 - risk * 2.0  # 94.0

    def test_buy_sl_tightened_near_support(self) -> None:
        config = SignalScoringConfig()
        service = ScannerService.__new__(ScannerService)
        service.scoring_config = config

        sr = {"near_support": True, "nearest_support": 99.0}
        sl = service._compute_stop_loss(100.0, 2.0, "BUY", sr)
        # Distance to support = 1.0, which is < 3.0 (ATR*1.5)
        # Tightened SL = 100 - 1.0 * 1.3 = 98.7
        assert sl == pytest.approx(98.7)

    def test_sell_sl_tightened_near_resistance(self) -> None:
        config = SignalScoringConfig()
        service = ScannerService.__new__(ScannerService)
        service.scoring_config = config

        sr = {"near_resistance": True, "nearest_resistance": 101.0}
        sl = service._compute_stop_loss(100.0, 2.0, "SELL", sr)
        # Distance to resistance = 1.0, which is < 3.0 (ATR*1.5)
        # Tightened SL = 100 + 1.0 * 1.3 = 101.3
        assert sl == pytest.approx(101.3)


class TestScannerServiceRationale:
    def test_buy_rationale(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False, "value": 25},
            "macd": {"bullish_crossover": True, "histogram_positive": True},
            "ema": {"bullish_crossover": False, "bullish_trend": True},
            "vwap": {"price_above_vwap": True},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False, "ratio": 1.1},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
        }
        rationale = ScannerService._generate_rationale("BUY", 65.0, indicators)
        assert "BUY signal" in rationale
        assert "confidence: 65%" in rationale
        assert "RSI oversold" in rationale
        assert "MACD bullish crossover" in rationale

    def test_sell_rationale(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"overbought": True, "dropping_from_overbought": True, "value": 78},
            "macd": {"bearish_crossover": True, "histogram_positive": False},
            "ema": {"bearish_crossover": False, "bearish_trend": True},
            "vwap": {"price_below_vwap": False},
            "bollinger": {"near_upper": True},
            "volume": {"spike": True, "ratio": 2.0},
            "support_resistance": {"near_resistance": True, "near_support": False, "nearest_resistance": 110},
            "week_52": {"near_high": False},
        }
        rationale = ScannerService._generate_rationale("SELL", 80.0, indicators)
        assert "SELL signal" in rationale
        assert "RSI overbought" in rationale
        assert "MACD bearish crossover" in rationale


class TestScannerServiceCRUD:
    async def test_list_signals_empty(self, scanner_service: ScannerService) -> None:
        signals = await scanner_service.list_signals()
        assert signals == []

    async def test_update_signal_status(self, db_session: AsyncSession, scanner_service: ScannerService) -> None:
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

        updated = await scanner_service.update_signal_status(signal.id, "executed")
        assert updated is not None
        assert updated.status == "executed"

    async def test_update_signal_expired_sets_timestamp(
        self, db_session: AsyncSession, scanner_service: ScannerService
    ) -> None:
        signal = Signal(
            tradingsymbol="TCS",
            exchange="NSE",
            signal_type="SELL",
            timeframe="15minute",
            entry_price=3500.0,
            stop_loss=3550.0,
            target_price=3400.0,
            confidence=55.0,
            indicators={},
            rationale="Test",
            status="active",
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)

        updated = await scanner_service.update_signal_status(signal.id, "expired")
        assert updated is not None
        assert updated.status == "expired"
        assert updated.expired_at is not None

    async def test_update_nonexistent_signal(self, scanner_service: ScannerService) -> None:
        result = await scanner_service.update_signal_status(999, "executed")
        assert result is None

    async def test_get_signal(self, db_session: AsyncSession, scanner_service: ScannerService) -> None:
        signal = Signal(
            tradingsymbol="INFY",
            exchange="NSE",
            signal_type="BUY",
            timeframe="15minute",
            entry_price=1500.0,
            stop_loss=1470.0,
            target_price=1560.0,
            confidence=70.0,
            indicators={"rsi": {"value": 28}},
            rationale="Test",
            status="active",
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)

        fetched = await scanner_service.get_signal(signal.id)
        assert fetched is not None
        assert fetched.tradingsymbol == "INFY"
        assert fetched.indicators == {"rsi": {"value": 28}}

    async def test_list_signals_filter_status(self, db_session: AsyncSession, scanner_service: ScannerService) -> None:
        for status in ("active", "active", "expired"):
            sig = Signal(
                tradingsymbol="RELIANCE",
                exchange="NSE",
                signal_type="BUY",
                timeframe="15minute",
                entry_price=2500.0,
                stop_loss=2460.0,
                target_price=2580.0,
                confidence=60.0,
                indicators={},
                rationale="Test",
                status=status,
            )
            db_session.add(sig)
        await db_session.commit()

        active = await scanner_service.list_signals(status="active")
        assert len(active) == 2
        expired = await scanner_service.list_signals(status="expired")
        assert len(expired) == 1

    async def test_scan_watchlist_empty(self, scanner_service: ScannerService) -> None:
        results, errors = await scanner_service.scan_watchlist()
        assert results == []
        assert errors == []

    async def test_scan_watchlist_with_items(self, db_session: AsyncSession) -> None:
        # Add watchlist item
        item = WatchlistItem(tradingsymbol="RELIANCE", exchange="NSE", notes="")
        db_session.add(item)
        await db_session.commit()

        service = ScannerService(db_session)
        with patch.object(service.market_data, "fetch_historical", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_candles(100)
            results, errors = await service.scan_watchlist()
        # Results depend on synthetic data scoring — just verify no crash
        assert isinstance(results, list)
        assert isinstance(errors, list)

    async def test_expire_old_signals(self, db_session: AsyncSession, scanner_service: ScannerService) -> None:
        old_signal = Signal(
            tradingsymbol="RELIANCE",
            exchange="NSE",
            signal_type="BUY",
            timeframe="15minute",
            entry_price=2500.0,
            stop_loss=2460.0,
            target_price=2580.0,
            confidence=60.0,
            indicators={},
            rationale="Test",
            status="active",
        )
        db_session.add(old_signal)
        await db_session.commit()
        await db_session.refresh(old_signal)

        # Manually backdate created_at
        old_signal.created_at = datetime.now(UTC) - timedelta(days=2)
        await db_session.commit()

        await scanner_service._expire_old_signals()

        await db_session.refresh(old_signal)
        assert old_signal.status == "expired"
        assert old_signal.expired_at is not None
