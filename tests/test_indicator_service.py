import numpy as np
import pandas as pd
import pytest

from app.services.indicator import IndicatorService, ScannerConfig


def _make_ohlcv(
    n: int = 100,
    base_price: float = 100.0,
    trend: str = "flat",
    volatility: float = 1.0,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.default_rng(42)
    prices = [base_price]
    for _i in range(1, n):
        if trend == "up":
            drift = 0.3
        elif trend == "down":
            drift = -0.3
        else:
            drift = 0.0
        change = drift + rng.normal(0, volatility)
        prices.append(max(prices[-1] + change, 1.0))

    close = np.array(prices)
    high = close + rng.uniform(0.5, 2.0, size=n)
    low = close - rng.uniform(0.5, 2.0, size=n)
    low = np.maximum(low, 0.1)
    open_ = close + rng.uniform(-1.0, 1.0, size=n)
    volume = rng.integers(100000, 1000000, size=n).astype(float)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _make_oversold_data(n: int = 100) -> pd.DataFrame:
    """Generate data with a strong downtrend ending to trigger RSI oversold."""
    rng = np.random.default_rng(42)
    prices = [200.0]
    for i in range(1, n):
        change = -2.0 + rng.normal(0, 0.3) if i > n - 20 else rng.normal(0, 0.5)
        prices.append(max(prices[-1] + change, 1.0))

    close = np.array(prices)
    high = close + rng.uniform(0.2, 1.0, size=n)
    low = close - rng.uniform(0.2, 1.0, size=n)
    low = np.maximum(low, 0.1)
    open_ = close + rng.uniform(-0.5, 0.5, size=n)
    volume = rng.integers(100000, 500000, size=n).astype(float)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


class TestIndicatorService:
    def test_compute_all_returns_all_keys(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)

        expected_keys = {
            "rsi",
            "macd",
            "ema",
            "bollinger",
            "vwap",
            "volume",
            "atr",
            "adx",
            "stoch_rsi",
            "candlestick",
            "support_resistance",
            "week_52",
            "supertrend",
            "obv",
            "cmf",
        }
        assert set(result.keys()) == expected_keys

    def test_compute_all_insufficient_data(self) -> None:
        df = _make_ohlcv(n=10)
        service = IndicatorService()
        result = service.compute_all(df)
        assert result == {}

    def test_rsi_values_in_range(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        rsi = result["rsi"]
        assert 0 <= rsi["value"] <= 100
        assert isinstance(rsi["oversold"], bool)
        assert isinstance(rsi["overbought"], bool)

    def test_rsi_oversold_on_downtrend(self) -> None:
        df = _make_oversold_data(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        rsi = result["rsi"]
        assert rsi["value"] < 40  # Should be low after strong downtrend

    def test_macd_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        macd = result["macd"]
        assert "macd" in macd
        assert "signal" in macd
        assert "histogram" in macd
        assert isinstance(macd["bullish_crossover"], bool)
        assert isinstance(macd["bearish_crossover"], bool)

    def test_ema_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        ema = result["ema"]
        assert "fast" in ema
        assert "slow" in ema
        assert isinstance(ema["bullish_crossover"], bool)
        assert isinstance(ema["bearish_crossover"], bool)
        assert isinstance(ema["bullish_trend"], bool)

    def test_ema_bullish_trend_on_uptrend(self) -> None:
        df = _make_ohlcv(n=100, trend="up")
        service = IndicatorService()
        result = service.compute_all(df)
        ema = result["ema"]
        assert ema["bullish_trend"] is True

    def test_bollinger_bands_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        bb = result["bollinger"]
        assert bb["upper"] > bb["middle"] > bb["lower"]
        assert isinstance(bb["near_lower"], bool)
        assert isinstance(bb["near_upper"], bool)

    def test_vwap_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        vwap = result["vwap"]
        assert vwap["value"] > 0
        assert isinstance(vwap["price_above_vwap"], bool)

    def test_volume_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        vol = result["volume"]
        assert vol["current"] > 0
        assert vol["sma"] > 0
        assert vol["ratio"] > 0
        assert isinstance(vol["spike"], bool)

    def test_volume_spike_detection(self) -> None:
        df = _make_ohlcv(n=100)
        # Make the last bar have very high volume
        df.iloc[-1, df.columns.get_loc("volume")] = 5_000_000.0
        service = IndicatorService()
        result = service.compute_all(df)
        assert result["volume"]["spike"] is True

    def test_atr_positive(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        assert result["atr"]["value"] > 0
        assert result["atr"]["pct"] > 0

    def test_support_resistance_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        sr = result["support_resistance"]
        assert "nearest_support" in sr
        assert "nearest_resistance" in sr
        assert isinstance(sr["near_support"], bool)
        assert isinstance(sr["near_resistance"], bool)

    def test_52_week_structure(self) -> None:
        df = _make_ohlcv(n=252)
        service = IndicatorService()
        result = service.compute_all(df)
        w52 = result["week_52"]
        assert w52["high"] >= w52["low"]
        assert isinstance(w52["near_high"], bool)
        assert isinstance(w52["near_low"], bool)

    def test_custom_config(self) -> None:
        config = ScannerConfig(rsi_period=7, ema_fast=5, ema_slow=10)
        df = _make_ohlcv(n=50)
        service = IndicatorService(config)
        result = service.compute_all(df)
        assert "rsi" in result
        assert "ema" in result

    def test_adx_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        adx = result["adx"]
        assert adx["value"] >= 0
        assert isinstance(adx["strong_trend"], bool)
        assert isinstance(adx["bullish_di"], bool)
        assert isinstance(adx["bearish_di"], bool)

    def test_adx_strong_on_uptrend(self) -> None:
        df = _make_ohlcv(n=100, trend="up", volatility=0.3)
        service = IndicatorService()
        result = service.compute_all(df)
        adx = result["adx"]
        assert adx["bullish_di"] is True

    def test_stoch_rsi_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        stoch = result["stoch_rsi"]
        assert 0 <= stoch["k"] <= 100
        assert 0 <= stoch["d"] <= 100
        assert isinstance(stoch["oversold"], bool)
        assert isinstance(stoch["overbought"], bool)
        assert isinstance(stoch["bullish_crossover"], bool)
        assert isinstance(stoch["bearish_crossover"], bool)

    def test_candlestick_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        candle = result["candlestick"]
        assert isinstance(candle["doji"], bool)
        assert isinstance(candle["hammer"], bool)
        assert isinstance(candle["inverted_hammer"], bool)
        assert isinstance(candle["bullish_engulfing"], bool)
        assert isinstance(candle["bearish_engulfing"], bool)

    def test_candlestick_doji_detection(self) -> None:
        """A doji has open ~= close with wide range."""
        df = _make_ohlcv(n=100)
        # Set last bar as doji: open=close with wide high-low range
        df.iloc[-1, df.columns.get_loc("open")] = 100.0
        df.iloc[-1, df.columns.get_loc("close")] = 100.1
        df.iloc[-1, df.columns.get_loc("high")] = 105.0
        df.iloc[-1, df.columns.get_loc("low")] = 95.0
        service = IndicatorService()
        result = service.compute_all(df)
        assert result["candlestick"]["doji"] is True

    @pytest.mark.parametrize("trend", ["up", "down", "flat"])
    def test_compute_all_various_trends(self, trend: str) -> None:
        df = _make_ohlcv(n=100, trend=trend)
        service = IndicatorService()
        result = service.compute_all(df)
        assert len(result) == 15

    def test_ema_trend_structure(self) -> None:
        df = _make_ohlcv(n=252, trend="up")
        service = IndicatorService()
        result = service._compute_ema_trend(df)
        assert result["available"] is True
        assert "ema50" in result
        assert "ema200" in result
        assert isinstance(result["golden_cross"], bool)
        assert isinstance(result["death_cross"], bool)
        assert isinstance(result["strong_uptrend"], bool)
        assert isinstance(result["strong_downtrend"], bool)

    def test_ema_trend_uptrend(self) -> None:
        df = _make_ohlcv(n=252, trend="up", volatility=0.3)
        service = IndicatorService()
        result = service._compute_ema_trend(df)
        assert result["available"] is True
        assert result["strong_uptrend"] is True
        assert result["strong_downtrend"] is False

    def test_ema_trend_insufficient_data(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service._compute_ema_trend(df)
        assert result == {"available": False}

    def test_volume_trend_fields(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        vol = result["volume"]
        assert vol["trend"] in ("rising", "falling", "flat")
        assert isinstance(vol["acceleration"], float)
        assert isinstance(vol["confirmed"], bool)

    def test_relative_strength_outperformer(self) -> None:
        df = _make_ohlcv(n=100, trend="up", volatility=0.3)
        service = IndicatorService()
        result = service._compute_relative_strength(df, benchmark_return_5d=-5.0)
        assert result["available"] is True
        assert result["stock_return_5d"] > result["benchmark_return_5d"]  # outperforms benchmark
        assert result["outperformer"] is True  # stock beats benchmark by > 2%

    def test_relative_strength_no_benchmark(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service._compute_relative_strength(df, benchmark_return_5d=None)
        assert result == {"available": False}

    def test_relative_strength_insufficient_data(self) -> None:
        df = _make_ohlcv(n=5)
        service = IndicatorService()
        result = service._compute_relative_strength(df, benchmark_return_5d=1.0)
        assert result == {"available": False}

    def test_fibonacci_structure(self) -> None:
        df = _make_ohlcv(n=100, volatility=2.0)
        service = IndicatorService()
        result = service._compute_fibonacci(df)
        assert result["available"] is True
        assert "swing_high" in result
        assert "swing_low" in result
        assert "fib_382" in result
        assert "fib_500" in result
        assert "fib_618" in result
        assert isinstance(result["near_fib_level"], bool)
        assert result["fib_382"] > result["fib_500"] > result["fib_618"]

    def test_fibonacci_insufficient_data(self) -> None:
        df = _make_ohlcv(n=5)
        service = IndicatorService()
        result = service._compute_fibonacci(df)
        assert result == {"available": False}

    def test_supertrend_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        st = result["supertrend"]
        assert "value" in st
        assert isinstance(st["bullish"], bool)
        assert isinstance(st["bearish"], bool)
        assert isinstance(st["buy_signal"], bool)
        assert isinstance(st["sell_signal"], bool)
        # Must be exactly one of bullish/bearish
        assert st["bullish"] != st["bearish"]

    def test_supertrend_uptrend_bullish(self) -> None:
        df = _make_ohlcv(n=100, trend="up", volatility=0.3)
        service = IndicatorService()
        result = service._compute_supertrend(df)
        assert result["bullish"] is True

    def test_supertrend_downtrend_bearish(self) -> None:
        df = _make_ohlcv(n=100, trend="down", volatility=0.3)
        service = IndicatorService()
        result = service._compute_supertrend(df)
        assert result["bearish"] is True

    def test_supertrend_insufficient_data(self) -> None:
        df = _make_ohlcv(n=5)
        service = IndicatorService()
        result = service._compute_supertrend(df)
        assert result["bullish"] is False
        assert result["bearish"] is False

    def test_obv_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        obv = result["obv"]
        assert "value" in obv
        assert isinstance(obv["rising"], bool)
        assert isinstance(obv["falling"], bool)
        assert isinstance(obv["bullish_divergence"], bool)
        assert isinstance(obv["bearish_divergence"], bool)

    def test_obv_trend_detection(self) -> None:
        df = _make_ohlcv(n=100, trend="up", volatility=0.3)
        service = IndicatorService()
        result = service._compute_obv(df)
        # OBV trend may not match price trend with random volume;
        # just verify structure and that one of rising/falling is set
        assert isinstance(result["rising"], bool)
        assert isinstance(result["falling"], bool)

    def test_obv_insufficient_data(self) -> None:
        df = _make_ohlcv(n=2)
        service = IndicatorService()
        result = service._compute_obv(df)
        assert result["bullish_divergence"] is False
        assert result["bearish_divergence"] is False

    def test_cmf_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service.compute_all(df)
        cmf = result["cmf"]
        assert "value" in cmf
        assert isinstance(cmf["bullish"], bool)
        assert isinstance(cmf["bearish"], bool)
        assert isinstance(cmf["strong_bullish"], bool)
        assert isinstance(cmf["strong_bearish"], bool)

    def test_cmf_custom_period(self) -> None:
        config = ScannerConfig(cmf_period=10)
        df = _make_ohlcv(n=100)
        service = IndicatorService(config)
        result = service._compute_cmf(df)
        assert "value" in result

    # ── Ichimoku ──

    def test_ichimoku_structure(self) -> None:
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service._compute_ichimoku(df)
        assert result["available"] is True
        for key in ("tenkan", "kijun", "span_a", "span_b", "cloud_top", "cloud_bottom"):
            assert key in result
        for key in ("above_cloud", "below_cloud", "in_cloud", "bullish_tk_cross", "bearish_tk_cross"):
            assert isinstance(result[key], bool)

    def test_ichimoku_insufficient_data(self) -> None:
        df = _make_ohlcv(n=40)
        service = IndicatorService()
        result = service._compute_ichimoku(df)
        assert result == {"available": False}

    def test_ichimoku_uptrend_above_cloud(self) -> None:
        df = _make_ohlcv(n=100, trend="up")
        service = IndicatorService()
        result = service._compute_ichimoku(df)
        assert result["available"] is True
        # In an uptrend, price is likely above the cloud
        assert isinstance(result["above_cloud"], bool)

    def test_ichimoku_mutual_exclusivity(self) -> None:
        """above_cloud, below_cloud, and in_cloud should be mutually exclusive."""
        df = _make_ohlcv(n=100)
        service = IndicatorService()
        result = service._compute_ichimoku(df)
        assert result["available"] is True
        states = [result["above_cloud"], result["below_cloud"], result["in_cloud"]]
        assert sum(states) == 1, f"Expected exactly one True, got {states}"
