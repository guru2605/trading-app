from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import ta


@dataclass(frozen=True)
class ScannerConfig:
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    ema_fast: int = 9
    ema_slow: int = 21
    bb_period: int = 20
    bb_std: int = 2
    volume_sma_period: int = 20
    volume_spike_ratio: float = 1.5
    atr_period: int = 14
    adx_period: int = 14
    adx_strong_trend: float = 25.0
    sr_lookback: int = 50
    sr_proximity_pct: float = 1.5
    high_52w_proximity_pct: float = 5.0
    low_52w_proximity_pct: float = 5.0
    stoch_rsi_period: int = 14
    stoch_rsi_oversold: float = 20.0
    stoch_rsi_overbought: float = 80.0
    candle_body_ratio: float = 0.3  # doji body <= 30% of range
    ema_medium: int = 50
    ema_long: int = 200
    fib_lookback: int = 50
    fib_proximity_pct: float = 1.0
    volume_trend_days: int = 3


class IndicatorService:
    """Pure computation service — takes a DataFrame, returns indicator dict."""

    def __init__(self, config: ScannerConfig | None = None) -> None:
        self.config = config or ScannerConfig()

    def compute_all(self, df: pd.DataFrame) -> dict[str, Any]:
        """Compute all technical indicators on an OHLCV DataFrame.

        Expected columns: open, high, low, close, volume
        Returns a dict with all indicator values for the latest bar.
        """
        if len(df) < self.config.ema_slow + 5:
            return {}

        result: dict[str, Any] = {}

        result["rsi"] = self._compute_rsi(df)
        result["macd"] = self._compute_macd(df)
        result["ema"] = self._compute_ema(df)
        result["bollinger"] = self._compute_bollinger(df)
        result["vwap"] = self._compute_vwap(df)
        result["volume"] = self._compute_volume(df)
        result["atr"] = self._compute_atr(df)
        result["adx"] = self._compute_adx(df)
        result["stoch_rsi"] = self._compute_stoch_rsi(df)
        result["candlestick"] = self._compute_candlestick_patterns(df)
        result["support_resistance"] = self._compute_support_resistance(df)
        result["week_52"] = self._compute_52_week(df)

        return result

    def _compute_rsi(self, df: pd.DataFrame) -> dict[str, Any]:
        rsi = ta.momentum.RSIIndicator(close=df["close"], window=self.config.rsi_period)
        rsi_values = rsi.rsi()
        current = float(rsi_values.iloc[-1]) if not rsi_values.empty else 50.0
        prev = float(rsi_values.iloc[-2]) if len(rsi_values) >= 2 else current
        return {
            "value": round(current, 2),
            "prev": round(prev, 2),
            "oversold": current < self.config.rsi_oversold,
            "overbought": current > self.config.rsi_overbought,
            "recovering_from_oversold": prev < self.config.rsi_oversold and current >= self.config.rsi_oversold,
            "dropping_from_overbought": prev > self.config.rsi_overbought and current <= self.config.rsi_overbought,
        }

    def _compute_macd(self, df: pd.DataFrame) -> dict[str, Any]:
        macd = ta.trend.MACD(
            close=df["close"],
            window_slow=self.config.macd_slow,
            window_fast=self.config.macd_fast,
            window_sign=self.config.macd_signal,
        )
        macd_line = macd.macd()
        signal_line = macd.macd_signal()
        histogram = macd.macd_diff()

        curr_macd = float(macd_line.iloc[-1]) if not macd_line.empty else 0.0
        curr_signal = float(signal_line.iloc[-1]) if not signal_line.empty else 0.0
        curr_hist = float(histogram.iloc[-1]) if not histogram.empty else 0.0
        prev_macd = float(macd_line.iloc[-2]) if len(macd_line) >= 2 else curr_macd
        prev_signal = float(signal_line.iloc[-2]) if len(signal_line) >= 2 else curr_signal

        bullish_crossover = prev_macd <= prev_signal and curr_macd > curr_signal
        bearish_crossover = prev_macd >= prev_signal and curr_macd < curr_signal

        return {
            "macd": round(curr_macd, 4),
            "signal": round(curr_signal, 4),
            "histogram": round(curr_hist, 4),
            "bullish_crossover": bullish_crossover,
            "bearish_crossover": bearish_crossover,
            "histogram_positive": curr_hist > 0,
        }

    def _compute_ema(self, df: pd.DataFrame) -> dict[str, Any]:
        ema_fast = ta.trend.EMAIndicator(close=df["close"], window=self.config.ema_fast).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(close=df["close"], window=self.config.ema_slow).ema_indicator()

        curr_fast = float(ema_fast.iloc[-1])
        curr_slow = float(ema_slow.iloc[-1])
        prev_fast = float(ema_fast.iloc[-2]) if len(ema_fast) >= 2 else curr_fast
        prev_slow = float(ema_slow.iloc[-2]) if len(ema_slow) >= 2 else curr_slow

        bullish_crossover = prev_fast <= prev_slow and curr_fast > curr_slow
        bearish_crossover = prev_fast >= prev_slow and curr_fast < curr_slow
        bullish_trend = curr_fast > curr_slow
        bearish_trend = curr_fast < curr_slow

        return {
            "fast": round(curr_fast, 2),
            "slow": round(curr_slow, 2),
            "bullish_crossover": bullish_crossover,
            "bearish_crossover": bearish_crossover,
            "bullish_trend": bullish_trend,
            "bearish_trend": bearish_trend,
        }

    def _compute_bollinger(self, df: pd.DataFrame) -> dict[str, Any]:
        bb = ta.volatility.BollingerBands(
            close=df["close"], window=self.config.bb_period, window_dev=self.config.bb_std
        )
        upper = float(bb.bollinger_hband().iloc[-1])
        middle = float(bb.bollinger_mavg().iloc[-1])
        lower = float(bb.bollinger_lband().iloc[-1])
        current_price = float(df["close"].iloc[-1])

        band_width = upper - lower
        near_lower = (current_price - lower) / band_width < 0.2 if band_width > 0 else False
        near_upper = (upper - current_price) / band_width < 0.2 if band_width > 0 else False

        return {
            "upper": round(upper, 2),
            "middle": round(middle, 2),
            "lower": round(lower, 2),
            "near_lower": near_lower,
            "near_upper": near_upper,
        }

    def _compute_vwap(self, df: pd.DataFrame) -> dict[str, Any]:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_tp_vol = (typical_price * df["volume"]).cumsum()
        cum_vol = df["volume"].cumsum()
        vwap = cum_tp_vol / cum_vol
        vwap = vwap.replace([np.inf, -np.inf], np.nan).ffill()

        current_vwap = float(vwap.iloc[-1]) if not vwap.empty else 0.0
        current_price = float(df["close"].iloc[-1])

        return {
            "value": round(current_vwap, 2),
            "price_above_vwap": current_price > current_vwap,
            "price_below_vwap": current_price < current_vwap,
        }

    def _compute_volume(self, df: pd.DataFrame) -> dict[str, Any]:
        vol_sma = df["volume"].rolling(window=self.config.volume_sma_period).mean()
        current_vol = float(df["volume"].iloc[-1])
        avg_vol = float(vol_sma.iloc[-1]) if not vol_sma.empty else current_vol

        ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

        # Volume trend: 3-day slope
        trend = "flat"
        acceleration = 1.0
        n = self.config.volume_trend_days
        if len(df) >= n + 1:
            recent_vols = df["volume"].iloc[-(n + 1) :].values
            prev_vol = float(recent_vols[-2])
            acceleration = current_vol / prev_vol if prev_vol > 0 else 1.0
            vol_start = float(recent_vols[0])
            vol_end = float(recent_vols[-1])
            if vol_end > vol_start * 1.1:
                trend = "rising"
            elif vol_end < vol_start * 0.9:
                trend = "falling"

        # Volume confirms price direction
        price_up = float(df["close"].iloc[-1]) > float(df["close"].iloc[-2]) if len(df) >= 2 else True
        confirmed = (price_up and trend == "rising") or (not price_up and trend == "rising")

        return {
            "current": current_vol,
            "sma": round(avg_vol, 0),
            "ratio": round(ratio, 2),
            "spike": ratio >= self.config.volume_spike_ratio,
            "trend": trend,
            "acceleration": round(acceleration, 2),
            "confirmed": confirmed,
        }

    def _compute_atr(self, df: pd.DataFrame) -> dict[str, Any]:
        atr = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=self.config.atr_period
        )
        current_atr = float(atr.average_true_range().iloc[-1])
        current_price = float(df["close"].iloc[-1])
        atr_pct = (current_atr / current_price * 100) if current_price > 0 else 0.0

        return {
            "value": round(current_atr, 2),
            "pct": round(atr_pct, 2),
        }

    def _compute_adx(self, df: pd.DataFrame) -> dict[str, Any]:
        adx = ta.trend.ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=self.config.adx_period)
        adx_value = float(adx.adx().iloc[-1])
        plus_di = float(adx.adx_pos().iloc[-1])
        minus_di = float(adx.adx_neg().iloc[-1])

        strong_trend = adx_value >= self.config.adx_strong_trend
        bullish_di = plus_di > minus_di
        bearish_di = minus_di > plus_di

        return {
            "value": round(adx_value, 2),
            "plus_di": round(plus_di, 2),
            "minus_di": round(minus_di, 2),
            "strong_trend": strong_trend,
            "bullish_di": bullish_di,
            "bearish_di": bearish_di,
        }

    def _compute_stoch_rsi(self, df: pd.DataFrame) -> dict[str, Any]:
        stoch_rsi = ta.momentum.StochRSIIndicator(
            close=df["close"], window=self.config.stoch_rsi_period, smooth1=3, smooth2=3
        )
        k = float(stoch_rsi.stochrsi_k().iloc[-1]) * 100
        d = float(stoch_rsi.stochrsi_d().iloc[-1]) * 100
        prev_k = float(stoch_rsi.stochrsi_k().iloc[-2]) * 100 if len(df) > 1 else k
        prev_d = float(stoch_rsi.stochrsi_d().iloc[-2]) * 100 if len(df) > 1 else d

        bullish_crossover = prev_k <= prev_d and k > d
        bearish_crossover = prev_k >= prev_d and k < d

        return {
            "k": round(k, 2),
            "d": round(d, 2),
            "oversold": k < self.config.stoch_rsi_oversold,
            "overbought": k > self.config.stoch_rsi_overbought,
            "bullish_crossover": bullish_crossover,
            "bearish_crossover": bearish_crossover,
        }

    def _compute_candlestick_patterns(self, df: pd.DataFrame) -> dict[str, Any]:
        """Detect key candlestick patterns on the last 3 bars."""
        o = df["open"].values
        h = df["high"].values
        lo = df["low"].values
        c = df["close"].values

        patterns: dict[str, Any] = {
            "doji": False,
            "hammer": False,
            "inverted_hammer": False,
            "bullish_engulfing": False,
            "bearish_engulfing": False,
        }

        if len(df) < 3:
            return patterns

        # Latest bar
        body = abs(c[-1] - o[-1])
        full_range = h[-1] - lo[-1]

        if full_range > 0:
            body_ratio = body / full_range

            # Doji: tiny body relative to range
            if body_ratio <= self.config.candle_body_ratio:
                patterns["doji"] = True

            # Hammer: small body at top, long lower shadow
            lower_shadow = min(o[-1], c[-1]) - lo[-1]
            upper_shadow = h[-1] - max(o[-1], c[-1])
            if lower_shadow >= body * 2 and upper_shadow < body:
                patterns["hammer"] = True

            # Inverted hammer: small body at bottom, long upper shadow
            if upper_shadow >= body * 2 and lower_shadow < body:
                patterns["inverted_hammer"] = True

        # Engulfing patterns (previous + current bar)
        prev_body = c[-2] - o[-2]
        curr_body = c[-1] - o[-1]

        # Bullish engulfing: previous red, current green engulfs previous
        if prev_body < 0 and curr_body > 0 and o[-1] <= c[-2] and c[-1] >= o[-2]:
            patterns["bullish_engulfing"] = True

        # Bearish engulfing: previous green, current red engulfs previous
        if prev_body > 0 and curr_body < 0 and o[-1] >= c[-2] and c[-1] <= o[-2]:
            patterns["bearish_engulfing"] = True

        return patterns

    def _compute_support_resistance(self, df: pd.DataFrame) -> dict[str, Any]:
        lookback = min(self.config.sr_lookback, len(df))
        recent = df.tail(lookback)
        current_price = float(df["close"].iloc[-1])

        # Swing highs and lows using a 5-bar window
        highs: list[float] = []
        lows: list[float] = []
        high_vals = recent["high"].values
        low_vals = recent["low"].values

        for i in range(2, len(recent) - 2):
            if (
                high_vals[i] > high_vals[i - 1]
                and high_vals[i] > high_vals[i - 2]
                and high_vals[i] > high_vals[i + 1]
                and high_vals[i] > high_vals[i + 2]
            ):
                highs.append(float(high_vals[i]))
            if (
                low_vals[i] < low_vals[i - 1]
                and low_vals[i] < low_vals[i - 2]
                and low_vals[i] < low_vals[i + 1]
                and low_vals[i] < low_vals[i + 2]
            ):
                lows.append(float(low_vals[i]))

        # Find nearest support (below price) and resistance (above price)
        supports = sorted([s for s in lows if s < current_price], reverse=True)
        resistances = sorted([r for r in highs if r > current_price])

        nearest_support = supports[0] if supports else None
        nearest_resistance = resistances[0] if resistances else None

        proximity_threshold = current_price * self.config.sr_proximity_pct / 100

        near_support = nearest_support is not None and (current_price - nearest_support) <= proximity_threshold
        near_resistance = nearest_resistance is not None and (nearest_resistance - current_price) <= proximity_threshold

        return {
            "nearest_support": round(nearest_support, 2) if nearest_support else None,
            "nearest_resistance": round(nearest_resistance, 2) if nearest_resistance else None,
            "near_support": near_support,
            "near_resistance": near_resistance,
        }

    def _compute_52_week(self, df: pd.DataFrame) -> dict[str, Any]:
        # Use all available data (ideally 252 trading days for 52 weeks)
        high_52w = float(df["high"].max())
        low_52w = float(df["low"].min())
        current_price = float(df["close"].iloc[-1])

        near_high = (
            (high_52w - current_price) / high_52w * 100 <= self.config.high_52w_proximity_pct if high_52w > 0 else False
        )
        near_low = (
            (current_price - low_52w) / low_52w * 100 <= self.config.low_52w_proximity_pct if low_52w > 0 else False
        )

        return {
            "high": round(high_52w, 2),
            "low": round(low_52w, 2),
            "near_high": near_high,
            "near_low": near_low,
        }

    def _compute_ema_trend(self, df: pd.DataFrame) -> dict[str, Any]:
        """Compute EMA 50/200 trend on daily data. Requires 205+ bars."""
        if len(df) < self.config.ema_long + 5:
            return {"available": False}

        ema50 = ta.trend.EMAIndicator(close=df["close"], window=self.config.ema_medium).ema_indicator()
        ema200 = ta.trend.EMAIndicator(close=df["close"], window=self.config.ema_long).ema_indicator()

        curr_ema50 = float(ema50.iloc[-1])
        curr_ema200 = float(ema200.iloc[-1])
        prev_ema50 = float(ema50.iloc[-2])
        prev_ema200 = float(ema200.iloc[-2])
        current_price = float(df["close"].iloc[-1])

        golden_cross = prev_ema50 <= prev_ema200 and curr_ema50 > curr_ema200
        death_cross = prev_ema50 >= prev_ema200 and curr_ema50 < curr_ema200
        strong_uptrend = current_price > curr_ema50 > curr_ema200
        strong_downtrend = current_price < curr_ema50 < curr_ema200

        return {
            "available": True,
            "ema50": round(curr_ema50, 2),
            "ema200": round(curr_ema200, 2),
            "golden_cross": golden_cross,
            "death_cross": death_cross,
            "strong_uptrend": strong_uptrend,
            "strong_downtrend": strong_downtrend,
        }

    def _compute_relative_strength(self, df: pd.DataFrame, benchmark_return_5d: float | None) -> dict[str, Any]:
        """Compare stock's 5-day return to benchmark (Nifty 50)."""
        if benchmark_return_5d is None or len(df) < 6:
            return {"available": False}

        close_now = float(df["close"].iloc[-1])
        close_5d_ago = float(df["close"].iloc[-6])
        if close_5d_ago <= 0:
            return {"available": False}

        stock_return = (close_now - close_5d_ago) / close_5d_ago * 100
        relative_strength = stock_return - benchmark_return_5d

        return {
            "available": True,
            "stock_return_5d": round(stock_return, 2),
            "benchmark_return_5d": round(benchmark_return_5d, 2),
            "relative_strength": round(relative_strength, 2),
            "outperformer": relative_strength > 2.0,
            "underperformer": relative_strength < -2.0,
        }

    def _compute_fibonacci(self, df: pd.DataFrame) -> dict[str, Any]:
        """Calculate Fibonacci retracement levels from recent swing high/low."""
        lookback = min(self.config.fib_lookback, len(df))
        if lookback < 10:
            return {"available": False}

        recent = df.tail(lookback)
        swing_high = float(recent["high"].max())
        swing_low = float(recent["low"].min())
        current_price = float(df["close"].iloc[-1])

        diff = swing_high - swing_low
        if diff <= 0:
            return {"available": False}

        fib_382 = swing_high - diff * 0.382
        fib_500 = swing_high - diff * 0.500
        fib_618 = swing_high - diff * 0.618

        proximity = current_price * self.config.fib_proximity_pct / 100
        near_fib = (
            abs(current_price - fib_382) <= proximity
            or abs(current_price - fib_500) <= proximity
            or abs(current_price - fib_618) <= proximity
        )

        nearest_level: float | None = None
        min_dist = float("inf")
        for level in (fib_382, fib_500, fib_618):
            dist = abs(current_price - level)
            if dist < min_dist:
                min_dist = dist
                nearest_level = level

        return {
            "available": True,
            "swing_high": round(swing_high, 2),
            "swing_low": round(swing_low, 2),
            "fib_382": round(fib_382, 2),
            "fib_500": round(fib_500, 2),
            "fib_618": round(fib_618, 2),
            "near_fib_level": near_fib,
            "nearest_level": round(nearest_level, 2) if nearest_level is not None else None,
        }
