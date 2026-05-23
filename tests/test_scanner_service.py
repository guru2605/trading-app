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
            "volume": {"spike": True, "trend": "rising", "confirmed": True},
            "support_resistance": {"near_support": True, "near_resistance": True},
            "week_52": {"near_low": True},
            "adx": {"strong_trend": True, "bullish_di": True},
            "stoch_rsi": {"oversold": True, "bullish_crossover": True},
            "candlestick": {"hammer": True, "bullish_engulfing": True},
            "relative_strength": {"available": True, "outperformer": True, "underperformer": False},
            "fibonacci": {"near_fib_level": True},
            "delivery": {"available": True, "delivery_pct": 70},
            "sentiment": {"available": True, "positive_sentiment": True, "negative_sentiment": False},
            "fii_dii": {"available": True, "fii_buying": True, "fii_selling": False},
        }
        ema_trend = {
            "available": True,
            "strong_uptrend": True,
            "strong_downtrend": False,
            "golden_cross": False,
            "death_cross": False,
        }
        score = ScannerService._score_buy(indicators, ema_trend)
        # RSI: 30+15, MACD: 30+10, EMA: 22, VWAP: 10, BB: 15, Vol spike: 10, SR: 15, Breakout: 20, 52w: 3
        # ADX: 15, Stoch: 10+10, Candle: 7+10, EMA50/200: 20, RS: 15, VolTrend: 10, Fib: 10
        # Delivery: 15, Sentiment: 10, FII: 5, Confluence(4): 40 = 357
        assert score == 357

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
            "volume": {"spike": True, "trend": "rising", "confirmed": True},
            "support_resistance": {"near_resistance": True, "near_support": True},
            "week_52": {"near_high": True},
            "adx": {"strong_trend": True, "bearish_di": True},
            "stoch_rsi": {"overbought": True, "bearish_crossover": True},
            "candlestick": {"inverted_hammer": True, "bearish_engulfing": True},
            "relative_strength": {"available": True, "underperformer": True, "outperformer": False},
            "fibonacci": {"near_fib_level": True},
            "delivery": {"available": True, "delivery_pct": 70},
            "sentiment": {"available": True, "negative_sentiment": True, "positive_sentiment": False},
            "fii_dii": {"available": True, "fii_selling": True, "fii_buying": False},
        }
        ema_trend = {
            "available": True,
            "strong_downtrend": True,
            "strong_uptrend": False,
            "golden_cross": False,
            "death_cross": False,
        }
        score = ScannerService._score_sell(indicators, ema_trend)
        # RSI: 30+15, MACD: 30+10, EMA: 22, VWAP: 10, BB: 15, Vol spike: 10, SR: 15, Breakdown: 20, 52w: 3
        # ADX: 15, Stoch: 10+10, Candle: 7+10, EMA50/200: 20, RS: 15, VolTrend: 10, Fib: 10
        # Delivery: 15, Sentiment: 10, FII: 5, Confluence(4): 40 = 357
        assert score == 357

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
        # RSI: 30 (primary), MACD hist: 10, EMA trend: 8, VWAP: 10 = 58
        # Only 1 primary indicator, no confluence bonus
        assert score == 58

    def test_confluence_bonus_3_primary(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": True, "histogram_positive": False},
            "ema": {"bullish_crossover": True, "bullish_trend": True},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, MACD: 30, EMA: 22, Confluence(3): 25 = 107
        assert score == 107

    def test_trend_alignment_buy_uptrend(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
        }
        ema_trend = {
            "available": True,
            "strong_uptrend": True,
            "strong_downtrend": False,
            "golden_cross": False,
            "death_cross": False,
        }
        score = ScannerService._score_buy(indicators, ema_trend)
        # RSI: 30, EMA50/200 uptrend: 20 = 50
        assert score == 50

    def test_trend_counter_buy_downtrend(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
        }
        ema_trend = {
            "available": True,
            "strong_downtrend": True,
            "strong_uptrend": False,
            "golden_cross": False,
            "death_cross": False,
        }
        score = ScannerService._score_buy(indicators, ema_trend)
        # RSI: 30, EMA50/200 counter-trend: -15 = 15
        assert score == 15

    def test_mtf_confirmation_agree(self) -> None:
        daily_context = {
            "rsi": {
                "oversold": True,
                "recovering_from_oversold": False,
                "overbought": False,
                "dropping_from_overbought": False,
            },
            "macd": {"bullish_crossover": True, "histogram_positive": True, "bearish_crossover": False},
            "ema": {
                "bullish_trend": True,
                "bullish_crossover": False,
                "bearish_trend": False,
                "bearish_crossover": False,
            },
        }
        result = ScannerService._apply_mtf_confirmation(50.0, "BUY", daily_context)
        assert result == pytest.approx(60.0)  # 50 * 1.20

    def test_mtf_confirmation_disagree(self) -> None:
        daily_context = {
            "rsi": {
                "overbought": True,
                "dropping_from_overbought": True,
                "oversold": False,
                "recovering_from_oversold": False,
            },
            "macd": {"bearish_crossover": True, "bullish_crossover": False, "histogram_positive": False},
            "ema": {
                "bearish_trend": True,
                "bearish_crossover": False,
                "bullish_trend": False,
                "bullish_crossover": False,
            },
        }
        result = ScannerService._apply_mtf_confirmation(50.0, "BUY", daily_context)
        assert result == pytest.approx(42.5)  # 50 * 0.85

    def test_mtf_confirmation_empty(self) -> None:
        result = ScannerService._apply_mtf_confirmation(50.0, "BUY", {})
        assert result == 50.0

    def test_vix_filter_high_fear_buy(self) -> None:
        result = ScannerService._apply_vix_filter(50.0, "BUY", 30.0)
        assert result == pytest.approx(42.5)  # 50 * 0.85

    def test_vix_filter_high_fear_sell(self) -> None:
        result = ScannerService._apply_vix_filter(50.0, "SELL", 30.0)
        assert result == pytest.approx(55.0)  # 50 * 1.10

    def test_vix_filter_normal(self) -> None:
        result = ScannerService._apply_vix_filter(50.0, "BUY", 18.0)
        assert result == 50.0

    def test_vix_filter_low_complacency(self) -> None:
        result = ScannerService._apply_vix_filter(50.0, "BUY", 10.0)
        assert result == pytest.approx(45.0)  # 50 * 0.90

    def test_vix_filter_none(self) -> None:
        result = ScannerService._apply_vix_filter(50.0, "BUY", None)
        assert result == 50.0

    def test_relative_strength_buy_outperformer(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "relative_strength": {"available": True, "outperformer": True, "underperformer": False},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, RS: 15 = 45
        assert score == 45

    def test_relative_strength_buy_counter(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "relative_strength": {"available": True, "outperformer": False, "underperformer": True},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, RS counter: -10 = 20
        assert score == 20

    def test_volume_trend_buy_rising(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False, "trend": "rising", "confirmed": True},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, VolTrend: 10 = 40
        assert score == 40

    def test_volume_trend_buy_falling(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False, "trend": "falling", "confirmed": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, VolTrend falling: -5 = 25
        assert score == 25

    def test_fibonacci_buy(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "fibonacci": {"near_fib_level": True},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, Fib: 10 = 40
        assert score == 40

    def test_delivery_high_buy(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "delivery": {"available": True, "delivery_pct": 70},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, Delivery >60%: 15 = 45
        assert score == 45

    def test_delivery_low_buy(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "delivery": {"available": True, "delivery_pct": 20},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, Delivery <30%: -10 = 20
        assert score == 20

    def test_sentiment_positive_buy(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "sentiment": {"available": True, "positive_sentiment": True, "negative_sentiment": False},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, Sentiment: 10 = 40
        assert score == 40

    def test_sentiment_negative_buy(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "sentiment": {"available": True, "positive_sentiment": False, "negative_sentiment": True},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, Sentiment counter: -5 = 25
        assert score == 25

    def test_fii_buying_buy(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"oversold": True, "recovering_from_oversold": False},
            "macd": {"bullish_crossover": False, "histogram_positive": False},
            "ema": {"bullish_crossover": False, "bullish_trend": False},
            "vwap": {"price_above_vwap": False},
            "bollinger": {"near_lower": False},
            "volume": {"spike": False},
            "support_resistance": {"near_support": False, "near_resistance": False},
            "week_52": {"near_low": False},
            "fii_dii": {"available": True, "fii_buying": True, "fii_selling": False},
        }
        score = ScannerService._score_buy(indicators)
        # RSI: 30, FII: 5 = 35
        assert score == 35

    def test_fii_selling_sell(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"overbought": True, "dropping_from_overbought": False},
            "macd": {"bearish_crossover": False, "histogram_positive": True},
            "ema": {"bearish_crossover": False, "bearish_trend": False},
            "vwap": {"price_below_vwap": False},
            "bollinger": {"near_upper": False},
            "volume": {"spike": False},
            "support_resistance": {"near_resistance": False, "near_support": False},
            "week_52": {"near_high": False},
            "fii_dii": {"available": True, "fii_selling": True, "fii_buying": False},
        }
        score = ScannerService._score_sell(indicators)
        # RSI: 30, FII: 5 = 35
        assert score == 35

    async def test_earnings_filter_near(self) -> None:
        service = ScannerService.__new__(ScannerService)
        service.market_data = AsyncMock()
        # Earnings in 2 days
        service.market_data.fetch_earnings_date = AsyncMock(return_value=datetime.now(UTC) + timedelta(days=2))
        result = await service._apply_earnings_filter(50.0, "RELIANCE", "NSE")
        assert result == pytest.approx(40.0)  # 50 * 0.80

    async def test_earnings_filter_far(self) -> None:
        service = ScannerService.__new__(ScannerService)
        service.market_data = AsyncMock()
        # Earnings in 10 days — no penalty
        service.market_data.fetch_earnings_date = AsyncMock(return_value=datetime.now(UTC) + timedelta(days=10))
        result = await service._apply_earnings_filter(50.0, "RELIANCE", "NSE")
        assert result == 50.0

    async def test_earnings_filter_none(self) -> None:
        service = ScannerService.__new__(ScannerService)
        service.market_data = AsyncMock()
        service.market_data.fetch_earnings_date = AsyncMock(return_value=None)
        result = await service._apply_earnings_filter(50.0, "RELIANCE", "NSE")
        assert result == 50.0


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
        with (
            patch.object(service.market_data, "fetch_historical", new_callable=AsyncMock) as mock_fetch,
            patch.object(service.market_data, "fetch_vix", new_callable=AsyncMock) as mock_vix,
            patch.object(service.market_data, "fetch_nifty_return_5d", new_callable=AsyncMock) as mock_nifty,
            patch.object(service.market_data, "fetch_earnings_date", new_callable=AsyncMock) as mock_earnings,
            patch.object(service.nse_data, "fetch_fii_dii_activity", new_callable=AsyncMock) as mock_fii,
            patch.object(service.nse_data, "fetch_delivery_data", new_callable=AsyncMock) as mock_delivery,
            patch.object(service.sentiment, "fetch_sentiment", new_callable=AsyncMock) as mock_sentiment,
        ):
            mock_fetch.return_value = _make_candles(100)
            mock_vix.return_value = None
            mock_nifty.return_value = None
            mock_earnings.return_value = None
            mock_fii.return_value = {"available": False}
            mock_delivery.return_value = {"available": False}
            mock_sentiment.return_value = {"available": False}
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
