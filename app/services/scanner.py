import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.models.signal import Signal
from app.models.watchlist_item import WatchlistItem
from app.schemas.scanner import ScanResultItem, SignalResponse
from app.services.indicator import IndicatorService, ScannerConfig
from app.services.market_data import MarketDataService
from app.services.nse_data import NseDataService
from app.services.sentiment import SentimentService


@dataclass(frozen=True)
class SignalScoringConfig:
    min_confidence: float = 40.0
    atr_sl_multiplier: float = 1.5
    risk_reward_ratio: float = 2.0
    sr_sl_tightening_pct: float = 0.3  # tighten SL by 30% when near S/R
    max_raw_score: float = (
        250.0  # Realistic strong signal (theoretical max ~357, but typical strong signals hit 150-200)
    )


class ScannerService:
    def __init__(
        self,
        db: AsyncSession,
        kite: KiteClient | None = None,
        scanner_config: ScannerConfig | None = None,
        scoring_config: SignalScoringConfig | None = None,
    ) -> None:
        self.db = db
        self.kite = kite
        self.market_data = MarketDataService()
        self.indicator_service = IndicatorService(scanner_config)
        self.scoring_config = scoring_config or SignalScoringConfig()
        self.nse_data = NseDataService()
        self.sentiment = SentimentService()
        self._semaphore = asyncio.Semaphore(3)

    async def scan_watchlist(self, timeframe: str = "15minute") -> tuple[list[ScanResultItem], list[str]]:
        """Scan all watchlist symbols and generate signals. Returns (results, errors)."""
        # Expire old signals
        await self._expire_old_signals()

        errors: list[str] = []

        # Fetch watchlist
        result = await self.db.execute(select(WatchlistItem))
        watchlist = list(result.scalars().all())
        if not watchlist:
            return [], []

        # Fetch market context once for the entire scan
        vix_value, nifty_return, fii_dii = await asyncio.gather(
            self.market_data.fetch_vix(),
            self.market_data.fetch_nifty_return_5d(),
            self.nse_data.fetch_fii_dii_activity(),
        )

        # Fetch historical data and compute signals concurrently
        tasks = []
        for item in watchlist:
            tasks.append(
                self._process_symbol(item.tradingsymbol, item.exchange, timeframe, vix_value, nifty_return, fii_dii)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        scan_results, errors = self._collect_results(results, [item.tradingsymbol for item in watchlist])
        await self._persist_signals(scan_results)
        return [r for r, _ in scan_results], errors

    async def scan_symbols(
        self, symbols: list[tuple[str, str]], timeframe: str = "15minute"
    ) -> tuple[list[ScanResultItem], list[str]]:
        """Scan an explicit list of (tradingsymbol, exchange) pairs."""
        await self._expire_old_signals()

        if not symbols:
            return [], []

        # Fetch market context once for the entire scan
        vix_value, nifty_return, fii_dii = await asyncio.gather(
            self.market_data.fetch_vix(),
            self.market_data.fetch_nifty_return_5d(),
            self.nse_data.fetch_fii_dii_activity(),
        )

        tasks = [self._process_symbol(sym, exch, timeframe, vix_value, nifty_return, fii_dii) for sym, exch in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scan_results, errors = self._collect_results(results, [sym for sym, _ in symbols])
        await self._persist_signals(scan_results)
        return [r for r, _ in scan_results], errors

    @staticmethod
    def _collect_results(
        results: list[tuple[ScanResultItem, Signal] | None | BaseException],
        symbol_names: list[str],
    ) -> tuple[list[tuple[ScanResultItem, Signal]], list[str]]:
        """Separate successful results from errors."""
        scan_results: list[tuple[ScanResultItem, Signal]] = []
        errors: list[str] = []
        for i, r in enumerate(results):
            if isinstance(r, tuple):
                scan_results.append(r)
            elif isinstance(r, Exception):
                sym = symbol_names[i] if i < len(symbol_names) else "unknown"
                errors.append(f"{sym}: {r}")
        return scan_results, errors

    async def _persist_signals(self, scan_results: list[tuple[ScanResultItem, Signal]]) -> None:
        """Upsert signals: update existing active signal for same symbol+timeframe, else create new."""
        if not scan_results:
            return
        for _, signal in scan_results:
            # Check for existing active signal with same symbol + timeframe
            result = await self.db.execute(
                select(Signal).where(
                    and_(
                        Signal.tradingsymbol == signal.tradingsymbol,
                        Signal.timeframe == signal.timeframe,
                        Signal.status == "active",
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                existing.exchange = signal.exchange
                existing.signal_type = signal.signal_type
                existing.entry_price = signal.entry_price
                existing.stop_loss = signal.stop_loss
                existing.target_price = signal.target_price
                existing.confidence = signal.confidence
                existing.indicators = signal.indicators
                existing.rationale = signal.rationale
                existing.created_at = datetime.now(UTC)
            else:
                self.db.add(signal)
        await self.db.commit()

    async def _process_symbol(
        self,
        tradingsymbol: str,
        exchange: str,
        timeframe: str,
        vix_value: float | None = None,
        nifty_return: float | None = None,
        fii_dii: dict[str, Any] | None = None,
    ) -> tuple[ScanResultItem, Signal] | None:
        """Fetch candles, compute indicators, and score one symbol. Does NOT touch the DB."""
        async with self._semaphore:
            if timeframe == "day":
                candles = await self._fetch_candles(tradingsymbol, exchange, timeframe)
                daily_candles = candles
            else:
                candles, daily_candles = await asyncio.gather(
                    self._fetch_candles(tradingsymbol, exchange, timeframe),
                    self._fetch_candles(tradingsymbol, exchange, "day"),
                )

        if not candles:
            return None

        df = self._candles_to_dataframe(candles)
        if df.empty or len(df) < 30:
            return None

        indicators = self.indicator_service.compute_all(df)
        if not indicators:
            return None

        # Compute daily context (EMA 50/200 + key daily indicators for MTF)
        daily_context: dict[str, Any] = {}
        ema_trend: dict[str, Any] | None = None
        if daily_candles:
            daily_df = self._candles_to_dataframe(daily_candles)
            if not daily_df.empty and len(daily_df) >= 30:
                ema_trend = self.indicator_service._compute_ema_trend(daily_df)
                if ema_trend.get("available"):
                    daily_context["ema_trend"] = ema_trend
                daily_context["rsi"] = self.indicator_service._compute_rsi(daily_df)
                daily_context["macd"] = self.indicator_service._compute_macd(daily_df)
                daily_context["ema"] = self.indicator_service._compute_ema(daily_df)

        # Phase 2: Compute relative strength vs Nifty and fibonacci
        relative_strength = self.indicator_service._compute_relative_strength(df, nifty_return)
        if relative_strength.get("available"):
            indicators["relative_strength"] = relative_strength

        fibonacci = self.indicator_service._compute_fibonacci(df)
        if fibonacci.get("available"):
            indicators["fibonacci"] = fibonacci

        # Phase 3: Fetch delivery data, sentiment, and store FII/DII
        delivery_data = await self.nse_data.fetch_delivery_data(tradingsymbol)
        if delivery_data.get("available"):
            indicators["delivery"] = delivery_data

        sentiment_data = await self.sentiment.fetch_sentiment(tradingsymbol)
        if sentiment_data.get("available"):
            indicators["sentiment"] = sentiment_data

        if fii_dii and fii_dii.get("available"):
            indicators["fii_dii"] = fii_dii

        buy_score = self._score_buy(indicators, ema_trend)
        sell_score = self._score_sell(indicators, ema_trend)

        # Pick the stronger signal
        if buy_score >= sell_score and buy_score > 0:
            signal_type = "BUY"
            raw_score = buy_score
        elif sell_score > buy_score and sell_score > 0:
            signal_type = "SELL"
            raw_score = sell_score
        else:
            return None

        confidence = min(raw_score / self.scoring_config.max_raw_score * 100, 100.0)
        if confidence < self.scoring_config.min_confidence:
            return None

        # Post-scoring multipliers (skip MTF when timeframe is daily — same data)
        if timeframe != "day":
            confidence = self._apply_mtf_confirmation(confidence, signal_type, daily_context)
        confidence = self._apply_vix_filter(confidence, signal_type, vix_value)
        confidence = await self._apply_earnings_filter(confidence, tradingsymbol, exchange)
        confidence = min(confidence, 100.0)

        if confidence < self.scoring_config.min_confidence:
            return None

        # Store daily context in indicators for frontend display
        if ema_trend and ema_trend.get("available"):
            indicators["ema_trend"] = ema_trend

        entry_price = float(df["close"].iloc[-1])
        atr_value = indicators.get("atr", {}).get("value", 0.0)
        sr = indicators.get("support_resistance", {})

        stop_loss = self._compute_stop_loss(entry_price, atr_value, signal_type, sr)
        target_price = self._compute_target(entry_price, stop_loss, signal_type)
        rationale = self._generate_rationale(signal_type, confidence, indicators)

        signal = Signal(
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            signal_type=signal_type,
            timeframe=timeframe,
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            confidence=round(confidence, 1),
            indicators=indicators,
            rationale=rationale,
            status="active",
        )

        result_item = ScanResultItem(
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            signal_type=signal_type,
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            confidence=round(confidence, 1),
            rationale=rationale,
        )

        return result_item, signal

    async def _fetch_candles(self, tradingsymbol: str, exchange: str, timeframe: str) -> list[dict[str, Any]]:
        to_date = datetime.now(UTC)
        if timeframe in ("5minute", "15minute", "30minute"):
            from_date = to_date - timedelta(days=7)
        else:
            from_date = to_date - timedelta(days=365)
        return await self.market_data.fetch_historical(tradingsymbol, exchange, from_date, to_date, timeframe)

    async def _expire_old_signals(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=2)
        result = await self.db.execute(select(Signal).where(Signal.status == "active", Signal.created_at < cutoff))
        old_signals = list(result.scalars().all())
        now = datetime.now(UTC)
        for sig in old_signals:
            sig.status = "expired"
            sig.expired_at = now
        if old_signals:
            await self.db.commit()

    @staticmethod
    def _candles_to_dataframe(candles: list[dict[str, Any]]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        df = pd.DataFrame(candles)
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    # ── Scoring ──

    @staticmethod
    def _score_buy(indicators: dict[str, Any], ema_trend: dict[str, Any] | None = None) -> float:
        score = 0.0
        primary_count = 0

        rsi = indicators.get("rsi", {})
        if rsi.get("oversold"):
            score += 30
            primary_count += 1
        if rsi.get("recovering_from_oversold"):
            score += 15
            primary_count += 1

        macd = indicators.get("macd", {})
        if macd.get("bullish_crossover"):
            score += 30
            primary_count += 1
        if macd.get("histogram_positive"):
            score += 10

        ema = indicators.get("ema", {})
        if ema.get("bullish_crossover"):
            score += 22
            primary_count += 1
        elif ema.get("bullish_trend"):
            score += 8

        vwap = indicators.get("vwap", {})
        if vwap.get("price_above_vwap"):
            score += 10

        bb = indicators.get("bollinger", {})
        if bb.get("near_lower"):
            score += 15

        vol = indicators.get("volume", {})
        if vol.get("spike"):
            score += 10

        sr = indicators.get("support_resistance", {})
        if sr.get("near_support"):
            score += 15

        # Breakout above resistance with volume
        if sr.get("near_resistance") and vol.get("spike"):
            score += 20

        w52 = indicators.get("week_52", {})
        if w52.get("near_low"):
            score += 3

        # ADX trend strength — boost if strong bullish trend
        adx = indicators.get("adx", {})
        if adx.get("strong_trend") and adx.get("bullish_di"):
            score += 15

        # Stochastic RSI
        stoch = indicators.get("stoch_rsi", {})
        if stoch.get("oversold"):
            score += 10
        if stoch.get("bullish_crossover"):
            score += 10

        # Candlestick patterns
        candle = indicators.get("candlestick", {})
        if candle.get("hammer"):
            score += 7
        if candle.get("bullish_engulfing"):
            score += 10

        # EMA 50/200 trend alignment
        if ema_trend and ema_trend.get("available"):
            if ema_trend.get("strong_uptrend") or ema_trend.get("golden_cross"):
                score += 20
            elif ema_trend.get("strong_downtrend") or ema_trend.get("death_cross"):
                score -= 15

        # Relative strength vs Nifty
        rs = indicators.get("relative_strength", {})
        if rs.get("available"):
            if rs.get("outperformer"):
                score += 15
            elif rs.get("underperformer"):
                score -= 10

        # Volume trend
        if vol.get("trend") == "rising" and vol.get("confirmed"):
            score += 10
        elif vol.get("trend") == "falling":
            score -= 5

        # Fibonacci retracement
        fib = indicators.get("fibonacci", {})
        if fib.get("near_fib_level"):
            score += 10

        # Delivery volume (Phase 3)
        delivery = indicators.get("delivery", {})
        if delivery.get("available"):
            dpct = delivery.get("delivery_pct", 0)
            if dpct > 60:
                score += 15
            elif dpct < 30:
                score -= 10

        # News sentiment (Phase 3)
        sentiment = indicators.get("sentiment", {})
        if sentiment.get("available"):
            if sentiment.get("positive_sentiment"):
                score += 10
            elif sentiment.get("negative_sentiment"):
                score -= 5

        # FII/DII flow (Phase 3)
        fii_dii = indicators.get("fii_dii", {})
        if fii_dii.get("available") and fii_dii.get("fii_buying"):
            score += 5

        # Confluence bonus: primary indicators agreement
        if primary_count >= 4:
            score += 40
        elif primary_count >= 3:
            score += 25

        return score

    @staticmethod
    def _score_sell(indicators: dict[str, Any], ema_trend: dict[str, Any] | None = None) -> float:
        score = 0.0
        primary_count = 0

        rsi = indicators.get("rsi", {})
        if rsi.get("overbought"):
            score += 30
            primary_count += 1
        if rsi.get("dropping_from_overbought"):
            score += 15
            primary_count += 1

        macd = indicators.get("macd", {})
        if macd.get("bearish_crossover"):
            score += 30
            primary_count += 1
        if not macd.get("histogram_positive"):
            score += 10

        ema = indicators.get("ema", {})
        if ema.get("bearish_crossover"):
            score += 22
            primary_count += 1
        elif ema.get("bearish_trend"):
            score += 8

        vwap = indicators.get("vwap", {})
        if vwap.get("price_below_vwap"):
            score += 10

        bb = indicators.get("bollinger", {})
        if bb.get("near_upper"):
            score += 15

        vol = indicators.get("volume", {})
        if vol.get("spike"):
            score += 10

        sr = indicators.get("support_resistance", {})
        if sr.get("near_resistance"):
            score += 15

        # Breakdown below support with volume
        if sr.get("near_support") and vol.get("spike"):
            score += 20

        w52 = indicators.get("week_52", {})
        if w52.get("near_high"):
            score += 3

        # ADX trend strength — boost if strong bearish trend
        adx = indicators.get("adx", {})
        if adx.get("strong_trend") and adx.get("bearish_di"):
            score += 15

        # Stochastic RSI
        stoch = indicators.get("stoch_rsi", {})
        if stoch.get("overbought"):
            score += 10
        if stoch.get("bearish_crossover"):
            score += 10

        # Candlestick patterns
        candle = indicators.get("candlestick", {})
        if candle.get("inverted_hammer"):
            score += 7
        if candle.get("bearish_engulfing"):
            score += 10

        # EMA 50/200 trend alignment
        if ema_trend and ema_trend.get("available"):
            if ema_trend.get("strong_downtrend") or ema_trend.get("death_cross"):
                score += 20
            elif ema_trend.get("strong_uptrend") or ema_trend.get("golden_cross"):
                score -= 15

        # Relative strength vs Nifty
        rs = indicators.get("relative_strength", {})
        if rs.get("available"):
            if rs.get("underperformer"):
                score += 15
            elif rs.get("outperformer"):
                score -= 10

        # Volume trend
        if vol.get("trend") == "rising" and vol.get("confirmed"):
            score += 10
        elif vol.get("trend") == "falling":
            score -= 5

        # Fibonacci retracement
        fib = indicators.get("fibonacci", {})
        if fib.get("near_fib_level"):
            score += 10

        # Delivery volume (Phase 3)
        delivery = indicators.get("delivery", {})
        if delivery.get("available"):
            dpct = delivery.get("delivery_pct", 0)
            if dpct > 60:
                score += 15
            elif dpct < 30:
                score -= 10

        # News sentiment (Phase 3)
        sentiment = indicators.get("sentiment", {})
        if sentiment.get("available"):
            if sentiment.get("negative_sentiment"):
                score += 10
            elif sentiment.get("positive_sentiment"):
                score -= 5

        # FII/DII flow (Phase 3)
        fii_dii = indicators.get("fii_dii", {})
        if fii_dii.get("available") and fii_dii.get("fii_selling"):
            score += 5

        # Confluence bonus: primary indicators agreement
        if primary_count >= 4:
            score += 40
        elif primary_count >= 3:
            score += 25

        return score

    # ── Post-scoring multipliers ──

    @staticmethod
    def _apply_mtf_confirmation(confidence: float, signal_type: str, daily_context: dict[str, Any]) -> float:
        if not daily_context:
            return confidence

        score = 0
        rsi = daily_context.get("rsi", {})
        if rsi.get("oversold") or rsi.get("recovering_from_oversold"):
            score += 1
        elif rsi.get("overbought") or rsi.get("dropping_from_overbought"):
            score -= 1

        macd = daily_context.get("macd", {})
        if macd.get("bullish_crossover") or macd.get("histogram_positive"):
            score += 1
        elif macd.get("bearish_crossover"):
            score -= 1

        ema = daily_context.get("ema", {})
        if ema.get("bullish_trend") or ema.get("bullish_crossover"):
            score += 1
        elif ema.get("bearish_trend") or ema.get("bearish_crossover"):
            score -= 1

        if score >= 2:
            daily_dir = "BUY"
        elif score <= -2:
            daily_dir = "SELL"
        else:
            daily_dir = "neutral"

        if daily_dir == signal_type:
            return confidence * 1.20
        elif daily_dir == "neutral":
            return confidence
        else:
            return confidence * 0.85

    @staticmethod
    def _apply_vix_filter(confidence: float, signal_type: str, vix_value: float | None) -> float:
        if vix_value is None:
            return confidence

        if vix_value > 25:
            if signal_type == "BUY":
                return confidence * 0.85
            else:
                return confidence * 1.10
        elif vix_value < 13:
            if signal_type == "BUY":
                return confidence * 0.90
            else:
                return confidence * 1.05

        return confidence

    async def _apply_earnings_filter(self, confidence: float, tradingsymbol: str, exchange: str) -> float:
        """Reduce confidence if earnings are within 3 trading days."""
        try:
            earnings_date = await self.market_data.fetch_earnings_date(tradingsymbol, exchange)
            if earnings_date is not None:
                now = datetime.now(UTC)
                # Make earnings_date offset-aware if it isn't
                if earnings_date.tzinfo is None:
                    earnings_date = earnings_date.replace(tzinfo=UTC)
                days_until = (earnings_date - now).days
                if 0 <= days_until <= 3:
                    return confidence * 0.80
        except Exception:
            pass  # best-effort, don't block the scan
        return confidence

    # ── SL / Target ──

    def _compute_stop_loss(self, entry: float, atr: float, signal_type: str, sr: dict[str, Any]) -> float:
        sl_distance = atr * self.scoring_config.atr_sl_multiplier

        # Tighten SL if near support (for BUY) or resistance (for SELL)
        if signal_type == "BUY" and sr.get("near_support") and sr.get("nearest_support"):
            support = sr["nearest_support"]
            sr_distance = entry - support
            if 0 < sr_distance < sl_distance:
                sl_distance = sr_distance * (1 + self.scoring_config.sr_sl_tightening_pct)

        if signal_type == "SELL" and sr.get("near_resistance") and sr.get("nearest_resistance"):
            resistance = sr["nearest_resistance"]
            sr_distance = resistance - entry
            if 0 < sr_distance < sl_distance:
                sl_distance = sr_distance * (1 + self.scoring_config.sr_sl_tightening_pct)

        if signal_type == "BUY":
            return entry - sl_distance
        return entry + sl_distance

    def _compute_target(self, entry: float, stop_loss: float, signal_type: str) -> float:
        risk = abs(entry - stop_loss)
        reward = risk * self.scoring_config.risk_reward_ratio
        if signal_type == "BUY":
            return entry + reward
        return entry - reward

    # ── Rationale ──

    @staticmethod
    def _generate_rationale(signal_type: str, confidence: float, indicators: dict[str, Any]) -> str:
        reasons: list[str] = []

        rsi = indicators.get("rsi", {})
        macd = indicators.get("macd", {})
        ema = indicators.get("ema", {})
        vwap = indicators.get("vwap", {})
        bb = indicators.get("bollinger", {})
        vol = indicators.get("volume", {})
        sr = indicators.get("support_resistance", {})
        w52 = indicators.get("week_52", {})
        adx = indicators.get("adx", {})
        stoch = indicators.get("stoch_rsi", {})
        candle = indicators.get("candlestick", {})
        ema_trend = indicators.get("ema_trend", {})

        rs = indicators.get("relative_strength", {})
        fib = indicators.get("fibonacci", {})
        delivery = indicators.get("delivery", {})
        sentiment = indicators.get("sentiment", {})
        fii_dii = indicators.get("fii_dii", {})

        if signal_type == "BUY":
            if rsi.get("oversold"):
                reasons.append(f"RSI oversold at {rsi.get('value', 'N/A')}")
            if rsi.get("recovering_from_oversold"):
                reasons.append("RSI recovering from oversold")
            if macd.get("bullish_crossover"):
                reasons.append("MACD bullish crossover")
            if macd.get("histogram_positive"):
                reasons.append("MACD histogram positive")
            if ema.get("bullish_crossover"):
                reasons.append("EMA 9/21 bullish crossover")
            elif ema.get("bullish_trend"):
                reasons.append("EMA 9 above EMA 21 (bullish trend)")
            if vwap.get("price_above_vwap"):
                reasons.append("Price above VWAP")
            if bb.get("near_lower"):
                reasons.append("Price near lower Bollinger Band")
            if vol.get("spike"):
                reasons.append(f"Volume spike ({vol.get('ratio', 'N/A')}x avg)")
            if vol.get("trend") == "rising" and vol.get("confirmed"):
                reasons.append("Volume trend rising (confirms direction)")
            elif vol.get("trend") == "falling":
                reasons.append("Volume trend falling (weak conviction)")
            if sr.get("near_support"):
                reasons.append(f"Near support at {sr.get('nearest_support', 'N/A')}")
            if sr.get("near_resistance") and vol.get("spike"):
                reasons.append("Breakout above resistance with volume")
            if w52.get("near_low"):
                reasons.append("Near 52-week low")
            if adx.get("strong_trend") and adx.get("bullish_di"):
                reasons.append(f"Strong bullish trend (ADX {adx.get('value', 'N/A')})")
            if stoch.get("oversold"):
                reasons.append("Stochastic RSI oversold")
            if stoch.get("bullish_crossover"):
                reasons.append("Stochastic RSI bullish crossover")
            if candle.get("hammer"):
                reasons.append("Hammer candlestick pattern")
            if candle.get("bullish_engulfing"):
                reasons.append("Bullish engulfing pattern")
            if ema_trend.get("available"):
                if ema_trend.get("strong_uptrend"):
                    reasons.append("Strong uptrend (price > EMA50 > EMA200)")
                elif ema_trend.get("golden_cross"):
                    reasons.append("Golden cross (EMA50 crossed above EMA200)")
                elif ema_trend.get("strong_downtrend") or ema_trend.get("death_cross"):
                    reasons.append("Counter-trend signal (against EMA50/200)")
            if rs.get("available"):
                if rs.get("outperformer"):
                    reasons.append(f"Outperforming Nifty by {rs.get('relative_strength', 0):.1f}%")
                elif rs.get("underperformer"):
                    reasons.append(f"Underperforming Nifty by {abs(rs.get('relative_strength', 0)):.1f}%")
            if fib.get("near_fib_level"):
                reasons.append(f"Near Fibonacci level {fib.get('nearest_level', 'N/A')}")
            if delivery.get("available"):
                dpct = delivery.get("delivery_pct", 0)
                if dpct > 60:
                    reasons.append(f"High delivery volume ({dpct:.0f}%)")
                elif dpct < 30:
                    reasons.append(f"Low delivery volume ({dpct:.0f}%) — speculative")
            if sentiment.get("positive_sentiment"):
                reasons.append("Positive news sentiment")
            elif sentiment.get("negative_sentiment"):
                reasons.append("Negative news sentiment (caution)")
            if fii_dii.get("available"):
                if fii_dii.get("fii_buying"):
                    reasons.append(f"FII net buyers ({fii_dii.get('fii_net', 0):.0f} Cr)")
                elif fii_dii.get("fii_selling"):
                    reasons.append(f"FII net sellers ({fii_dii.get('fii_net', 0):.0f} Cr)")
        else:
            if rsi.get("overbought"):
                reasons.append(f"RSI overbought at {rsi.get('value', 'N/A')}")
            if rsi.get("dropping_from_overbought"):
                reasons.append("RSI dropping from overbought")
            if macd.get("bearish_crossover"):
                reasons.append("MACD bearish crossover")
            if not macd.get("histogram_positive"):
                reasons.append("MACD histogram negative")
            if ema.get("bearish_crossover"):
                reasons.append("EMA 9/21 bearish crossover")
            elif ema.get("bearish_trend"):
                reasons.append("EMA 9 below EMA 21 (bearish trend)")
            if vwap.get("price_below_vwap"):
                reasons.append("Price below VWAP")
            if bb.get("near_upper"):
                reasons.append("Price near upper Bollinger Band")
            if vol.get("spike"):
                reasons.append(f"Volume spike ({vol.get('ratio', 'N/A')}x avg)")
            if vol.get("trend") == "rising" and vol.get("confirmed"):
                reasons.append("Volume trend rising (confirms direction)")
            elif vol.get("trend") == "falling":
                reasons.append("Volume trend falling (weak conviction)")
            if sr.get("near_resistance"):
                reasons.append(f"Near resistance at {sr.get('nearest_resistance', 'N/A')}")
            if sr.get("near_support") and vol.get("spike"):
                reasons.append("Breakdown below support with volume")
            if w52.get("near_high"):
                reasons.append("Near 52-week high")
            if adx.get("strong_trend") and adx.get("bearish_di"):
                reasons.append(f"Strong bearish trend (ADX {adx.get('value', 'N/A')})")
            if stoch.get("overbought"):
                reasons.append("Stochastic RSI overbought")
            if stoch.get("bearish_crossover"):
                reasons.append("Stochastic RSI bearish crossover")
            if candle.get("inverted_hammer"):
                reasons.append("Inverted hammer candlestick pattern")
            if candle.get("bearish_engulfing"):
                reasons.append("Bearish engulfing pattern")
            if ema_trend.get("available"):
                if ema_trend.get("strong_downtrend"):
                    reasons.append("Strong downtrend (price < EMA50 < EMA200)")
                elif ema_trend.get("death_cross"):
                    reasons.append("Death cross (EMA50 crossed below EMA200)")
                elif ema_trend.get("strong_uptrend") or ema_trend.get("golden_cross"):
                    reasons.append("Counter-trend signal (against EMA50/200)")
            if rs.get("available"):
                if rs.get("underperformer"):
                    reasons.append(f"Underperforming Nifty by {abs(rs.get('relative_strength', 0)):.1f}%")
                elif rs.get("outperformer"):
                    reasons.append(f"Outperforming Nifty by {rs.get('relative_strength', 0):.1f}%")
            if fib.get("near_fib_level"):
                reasons.append(f"Near Fibonacci level {fib.get('nearest_level', 'N/A')}")
            if delivery.get("available"):
                dpct = delivery.get("delivery_pct", 0)
                if dpct > 60:
                    reasons.append(f"High delivery volume ({dpct:.0f}%)")
                elif dpct < 30:
                    reasons.append(f"Low delivery volume ({dpct:.0f}%) — speculative")
            if sentiment.get("negative_sentiment"):
                reasons.append("Negative news sentiment")
            elif sentiment.get("positive_sentiment"):
                reasons.append("Positive news sentiment (caution)")
            if fii_dii.get("available"):
                if fii_dii.get("fii_selling"):
                    reasons.append(f"FII net sellers ({fii_dii.get('fii_net', 0):.0f} Cr)")
                elif fii_dii.get("fii_buying"):
                    reasons.append(f"FII net buyers ({fii_dii.get('fii_net', 0):.0f} Cr)")

        summary = f"{signal_type} signal (confidence: {confidence:.0f}%). "
        if reasons:
            summary += "Key factors: " + "; ".join(reasons) + "."
        return summary

    # ── Signal CRUD ──

    async def list_signals(
        self,
        status: str | None = None,
        signal_type: str | None = None,
        tradingsymbol: str | None = None,
        timeframe: str | None = None,
    ) -> list[SignalResponse]:
        query = select(Signal).order_by(Signal.created_at.desc())
        if status:
            query = query.where(Signal.status == status)
        if signal_type:
            query = query.where(Signal.signal_type == signal_type)
        if tradingsymbol:
            query = query.where(Signal.tradingsymbol == tradingsymbol.upper())
        if timeframe:
            query = query.where(Signal.timeframe == timeframe)
        result = await self.db.execute(query)
        signals = list(result.scalars().all())
        return [SignalResponse.model_validate(s) for s in signals]

    async def get_signal(self, signal_id: int) -> Signal | None:
        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        return result.scalar_one_or_none()

    async def expire_all_signals(self, tradingsymbols: list[str] | None = None) -> int:
        """Expire all active signals, optionally filtered to specific symbols."""
        query = select(Signal).where(Signal.status == "active")
        if tradingsymbols:
            query = query.where(Signal.tradingsymbol.in_(tradingsymbols))
        result = await self.db.execute(query)
        signals = list(result.scalars().all())
        now = datetime.now(UTC)
        for sig in signals:
            sig.status = "expired"
            sig.expired_at = now
        if signals:
            await self.db.commit()
        return len(signals)

    async def update_signal_status(self, signal_id: int, status: str) -> Signal | None:
        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        signal = result.scalar_one_or_none()
        if signal is None:
            return None
        signal.status = status
        if status == "expired":
            signal.expired_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(signal)
        return signal
