import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.models.instrument import Instrument
from app.models.signal import Signal
from app.models.watchlist_item import WatchlistItem
from app.schemas.scanner import ScanResultItem, SignalResponse
from app.services.indicator import IndicatorService, ScannerConfig


@dataclass(frozen=True)
class SignalScoringConfig:
    min_confidence: float = 40.0
    atr_sl_multiplier: float = 1.5
    risk_reward_ratio: float = 2.0
    sr_sl_tightening_pct: float = 0.3  # tighten SL by 30% when near S/R
    max_raw_score: float = 200.0  # increased for new indicators


class ScannerService:
    def __init__(
        self,
        db: AsyncSession,
        kite: KiteClient,
        scanner_config: ScannerConfig | None = None,
        scoring_config: SignalScoringConfig | None = None,
    ) -> None:
        self.db = db
        self.kite = kite
        self.indicator_service = IndicatorService(scanner_config)
        self.scoring_config = scoring_config or SignalScoringConfig()
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

        # Resolve instrument tokens
        symbols = [w.tradingsymbol for w in watchlist]
        exchanges = {w.tradingsymbol: w.exchange for w in watchlist}
        token_map = await self._resolve_tokens(symbols, exchanges)

        # Report unresolved symbols
        for item in watchlist:
            if item.tradingsymbol not in token_map:
                errors.append(f"{item.tradingsymbol}: instrument token not found. Run Sync Holdings first.")

        # Fetch historical data and compute signals concurrently
        tasks = []
        for item in watchlist:
            token = token_map.get(item.tradingsymbol)
            if token is None:
                continue
            tasks.append(self._process_symbol(item.tradingsymbol, item.exchange, token, timeframe))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        scan_results: list[ScanResultItem] = []
        for i, r in enumerate(results):
            if isinstance(r, ScanResultItem):
                scan_results.append(r)
            elif isinstance(r, Exception):
                # Find which symbol this error belongs to
                resolved_items = [it for it in watchlist if it.tradingsymbol in token_map]
                sym = resolved_items[i].tradingsymbol if i < len(resolved_items) else "unknown"
                errors.append(f"{sym}: {r}")

        return scan_results, errors

    async def _process_symbol(
        self, tradingsymbol: str, exchange: str, token: int, timeframe: str
    ) -> ScanResultItem | None:
        """Fetch candles, compute indicators, score, and persist signal for one symbol."""
        async with self._semaphore:
            candles = await self._fetch_candles(token, timeframe)

        if not candles:
            return None

        df = self._candles_to_dataframe(candles)
        if df.empty or len(df) < 30:
            return None

        indicators = self.indicator_service.compute_all(df)
        if not indicators:
            return None

        buy_score = self._score_buy(indicators)
        sell_score = self._score_sell(indicators)

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

        entry_price = float(df["close"].iloc[-1])
        atr_value = indicators.get("atr", {}).get("value", 0.0)
        sr = indicators.get("support_resistance", {})

        stop_loss = self._compute_stop_loss(entry_price, atr_value, signal_type, sr)
        target_price = self._compute_target(entry_price, stop_loss, signal_type)
        rationale = self._generate_rationale(signal_type, confidence, indicators)

        # Persist signal
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
        self.db.add(signal)
        await self.db.commit()
        await self.db.refresh(signal)

        return ScanResultItem(
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            signal_type=signal_type,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target_price=signal.target_price,
            confidence=signal.confidence,
            rationale=rationale,
        )

    async def _fetch_candles(self, token: int, timeframe: str) -> list[dict[str, Any]]:
        to_date = datetime.now(UTC)
        if timeframe in ("5minute", "15minute", "30minute"):
            from_date = to_date - timedelta(days=7)
        else:
            from_date = to_date - timedelta(days=365)
        return await self.kite.historical_data(token, from_date, to_date, timeframe)

    async def _resolve_tokens(self, symbols: list[str], exchanges: dict[str, str]) -> dict[str, int]:
        result = await self.db.execute(select(Instrument).where(Instrument.tradingsymbol.in_(symbols)))
        instruments = list(result.scalars().all())
        token_map: dict[str, int] = {}
        for inst in instruments:
            if inst.tradingsymbol in exchanges and inst.exchange == exchanges[inst.tradingsymbol]:
                token_map[inst.tradingsymbol] = inst.instrument_token
        return token_map

    async def _expire_old_signals(self) -> None:
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(select(Signal).where(Signal.status == "active", Signal.created_at < today_start))
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
    def _score_buy(indicators: dict[str, Any]) -> float:
        score = 0.0
        rsi = indicators.get("rsi", {})
        if rsi.get("oversold"):
            score += 20
        if rsi.get("recovering_from_oversold"):
            score += 10

        macd = indicators.get("macd", {})
        if macd.get("bullish_crossover"):
            score += 20
        if macd.get("histogram_positive"):
            score += 10

        ema = indicators.get("ema", {})
        if ema.get("bullish_crossover"):
            score += 15
        elif ema.get("bullish_trend"):
            score += 5

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
            score += 5

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
            score += 10
        if candle.get("bullish_engulfing"):
            score += 15

        return score

    @staticmethod
    def _score_sell(indicators: dict[str, Any]) -> float:
        score = 0.0
        rsi = indicators.get("rsi", {})
        if rsi.get("overbought"):
            score += 20
        if rsi.get("dropping_from_overbought"):
            score += 10

        macd = indicators.get("macd", {})
        if macd.get("bearish_crossover"):
            score += 20
        if not macd.get("histogram_positive"):
            score += 10

        ema = indicators.get("ema", {})
        if ema.get("bearish_crossover"):
            score += 15
        elif ema.get("bearish_trend"):
            score += 5

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
            score += 5

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
            score += 10
        if candle.get("bearish_engulfing"):
            score += 15

        return score

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
    ) -> list[SignalResponse]:
        query = select(Signal).order_by(Signal.created_at.desc())
        if status:
            query = query.where(Signal.status == status)
        if signal_type:
            query = query.where(Signal.signal_type == signal_type)
        if tradingsymbol:
            query = query.where(Signal.tradingsymbol == tradingsymbol.upper())
        result = await self.db.execute(query)
        signals = list(result.scalars().all())
        return [SignalResponse.model_validate(s) for s in signals]

    async def get_signal(self, signal_id: int) -> Signal | None:
        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        return result.scalar_one_or_none()

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
