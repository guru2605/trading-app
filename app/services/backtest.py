"""Backtesting framework — offline tool for evaluating scanner signal quality.

NOT in the live scanner path. Runs historical data through the indicator+scoring
pipeline, simulates entries/exits, and computes performance metrics.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.services.indicator import IndicatorService, ScannerConfig
from app.services.market_data import MarketDataService
from app.services.scanner import SignalScoringConfig

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """A simulated trade."""

    symbol: str
    signal_type: str  # "BUY" or "SELL"
    entry_bar: int
    entry_price: float
    stop_loss: float
    target_price: float
    confidence: float
    exit_bar: int | None = None
    exit_price: float | None = None
    outcome: str | None = None  # "win", "loss", "expired"
    pnl_pct: float = 0.0
    rr_achieved: float = 0.0


@dataclass
class BacktestResult:
    """Aggregate backtest metrics."""

    symbol: str
    timeframe: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0
    win_rate: float = 0.0
    avg_rr: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    trades: list[Trade] = field(default_factory=list)


class BacktestService:
    """Runs historical backtests using the same indicator and scoring pipeline as the live scanner."""

    def __init__(
        self,
        scanner_config: ScannerConfig | None = None,
        scoring_config: SignalScoringConfig | None = None,
        max_hold_bars: int = 20,
    ) -> None:
        self.indicator_service = IndicatorService(scanner_config)
        self.scoring_config = scoring_config or SignalScoringConfig()
        self.market_data = MarketDataService()
        self.max_hold_bars = max_hold_bars
        self._max_raw_score = self.scoring_config.max_raw_score

    async def run(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "day",
        lookback_bars: int = 50,
    ) -> BacktestResult:
        """Run a backtest on a single symbol.

        Slides a window of `lookback_bars` across the full history,
        computes indicators and scoring at each bar, simulates entries/exits.
        """
        candles = await self._fetch_full_history(symbol, exchange, timeframe)
        if not candles or len(candles) < lookback_bars + self.max_hold_bars:
            return BacktestResult(symbol=symbol, timeframe=timeframe)

        full_df = self._candles_to_dataframe(candles)
        if full_df.empty:
            return BacktestResult(symbol=symbol, timeframe=timeframe)

        trades: list[Trade] = []
        in_trade = False
        current_trade: Trade | None = None

        # Slide a window across the data
        for i in range(lookback_bars, len(full_df)):
            window = full_df.iloc[i - lookback_bars : i].copy().reset_index(drop=True)

            # If we're in a trade, check for exit
            if in_trade and current_trade is not None:
                bar = full_df.iloc[i]
                high = float(bar["high"])
                low = float(bar["low"])
                close = float(bar["close"])
                bars_held = i - current_trade.entry_bar

                exited = self._check_exit(current_trade, high, low, close, i, bars_held)
                if exited:
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                continue

            # Not in a trade — check for new signal
            if len(window) < 30:
                continue

            signal = self._evaluate_bar(window)
            if signal is not None:
                signal_type, raw_score, indicators = signal
                confidence = min(raw_score / self._max_raw_score * 100, 100.0)
                if confidence < self.scoring_config.min_confidence:
                    continue

                entry_price = float(window["close"].iloc[-1])
                atr_value = indicators.get("atr", {}).get("value", 0.0)
                sr = indicators.get("support_resistance", {})
                stop_loss = self._compute_stop_loss(entry_price, atr_value, signal_type, sr)
                target_price = self._compute_target(entry_price, stop_loss, signal_type)

                current_trade = Trade(
                    symbol=symbol,
                    signal_type=signal_type,
                    entry_bar=i,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    target_price=target_price,
                    confidence=round(confidence, 1),
                )
                in_trade = True

        # Close any open trade at end
        if in_trade and current_trade is not None:
            last_close = float(full_df["close"].iloc[-1])
            current_trade.exit_bar = len(full_df) - 1
            current_trade.exit_price = last_close
            current_trade.outcome = "expired"
            current_trade.pnl_pct = self._compute_pnl_pct(current_trade, last_close)
            trades.append(current_trade)

        return self._compute_metrics(trades, symbol, timeframe)

    async def compare(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "day",
        alt_scoring_config: SignalScoringConfig | None = None,
        alt_scanner_config: ScannerConfig | None = None,
    ) -> dict[str, BacktestResult]:
        """A/B comparison: run backtest with current config vs alternative config."""
        result_a = await self.run(symbol, exchange, timeframe)

        alt_service = BacktestService(
            scanner_config=alt_scanner_config,
            scoring_config=alt_scoring_config or self.scoring_config,
            max_hold_bars=self.max_hold_bars,
        )
        result_b = await alt_service.run(symbol, exchange, timeframe)

        return {"current": result_a, "proposed": result_b}

    def _evaluate_bar(self, window: pd.DataFrame) -> tuple[str, float, dict[str, Any]] | None:
        """Compute indicators and score a single bar window. Returns (signal_type, raw_score, indicators) or None."""
        from app.services.scanner import ScannerService

        indicators = self.indicator_service.compute_all(window)
        if not indicators:
            return None

        buy_score = ScannerService._score_buy(indicators)
        sell_score = ScannerService._score_sell(indicators)

        if buy_score >= sell_score and buy_score > 0:
            return "BUY", buy_score, indicators
        elif sell_score > buy_score and sell_score > 0:
            return "SELL", sell_score, indicators
        return None

    def _compute_stop_loss(self, entry: float, atr: float, signal_type: str, sr: dict[str, Any]) -> float:
        sl_distance = atr * self.scoring_config.atr_sl_multiplier
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

    def _check_exit(
        self,
        trade: Trade,
        high: float,
        low: float,
        close: float,
        bar_idx: int,
        bars_held: int,
    ) -> bool:
        """Check if a trade should be exited. Returns True if exited."""
        if trade.signal_type == "BUY":
            if high >= trade.target_price:
                trade.exit_bar = bar_idx
                trade.exit_price = trade.target_price
                trade.outcome = "win"
                trade.pnl_pct = self._compute_pnl_pct(trade, trade.target_price)
                trade.rr_achieved = self._compute_rr(trade)
                return True
            if low <= trade.stop_loss:
                trade.exit_bar = bar_idx
                trade.exit_price = trade.stop_loss
                trade.outcome = "loss"
                trade.pnl_pct = self._compute_pnl_pct(trade, trade.stop_loss)
                trade.rr_achieved = self._compute_rr(trade)
                return True
        else:  # SELL
            if low <= trade.target_price:
                trade.exit_bar = bar_idx
                trade.exit_price = trade.target_price
                trade.outcome = "win"
                trade.pnl_pct = self._compute_pnl_pct(trade, trade.target_price)
                trade.rr_achieved = self._compute_rr(trade)
                return True
            if high >= trade.stop_loss:
                trade.exit_bar = bar_idx
                trade.exit_price = trade.stop_loss
                trade.outcome = "loss"
                trade.pnl_pct = self._compute_pnl_pct(trade, trade.stop_loss)
                trade.rr_achieved = self._compute_rr(trade)
                return True

        # Time-based expiry
        if bars_held >= self.max_hold_bars:
            trade.exit_bar = bar_idx
            trade.exit_price = close
            trade.outcome = "expired"
            trade.pnl_pct = self._compute_pnl_pct(trade, close)
            trade.rr_achieved = self._compute_rr(trade)
            return True

        return False

    @staticmethod
    def _compute_pnl_pct(trade: Trade, exit_price: float) -> float:
        if trade.entry_price == 0:
            return 0.0
        if trade.signal_type == "BUY":
            return (exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            return (trade.entry_price - exit_price) / trade.entry_price * 100

    @staticmethod
    def _compute_rr(trade: Trade) -> float:
        """Compute actual risk:reward achieved."""
        if trade.exit_price is None or trade.entry_price == 0:
            return 0.0
        risk = abs(trade.entry_price - trade.stop_loss)
        if risk == 0:
            return 0.0
        if trade.signal_type == "BUY":
            reward = trade.exit_price - trade.entry_price
        else:
            reward = trade.entry_price - trade.exit_price
        return reward / risk

    def _compute_metrics(self, trades: list[Trade], symbol: str, timeframe: str) -> BacktestResult:
        """Compute aggregate performance metrics from trade list."""
        result = BacktestResult(symbol=symbol, timeframe=timeframe, trades=trades)
        if not trades:
            return result

        result.total_trades = len(trades)
        result.wins = sum(1 for t in trades if t.outcome == "win")
        result.losses = sum(1 for t in trades if t.outcome == "loss")
        result.expired = sum(1 for t in trades if t.outcome == "expired")
        result.win_rate = result.wins / result.total_trades * 100 if result.total_trades > 0 else 0.0

        pnls = [t.pnl_pct for t in trades]
        result.total_return_pct = sum(pnls)
        result.avg_rr = float(np.mean([t.rr_achieved for t in trades])) if trades else 0.0

        # Max drawdown
        cumulative = np.cumsum(pnls)
        peak = np.maximum.accumulate(cumulative)
        drawdowns = cumulative - peak
        result.max_drawdown_pct = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Sharpe ratio (assuming daily bars, annualized)
        if len(pnls) > 1:
            pnl_arr = np.array(pnls)
            mean_ret = float(np.mean(pnl_arr))
            std_ret = float(np.std(pnl_arr, ddof=1))
            if std_ret > 0:
                result.sharpe_ratio = round(mean_ret / std_ret * math.sqrt(252), 2)

        # Profit factor
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        if gross_loss > 0:
            result.profit_factor = round(gross_profit / gross_loss, 2)
        elif gross_profit > 0:
            result.profit_factor = float("inf")

        # Round floats
        result.win_rate = round(result.win_rate, 1)
        result.total_return_pct = round(result.total_return_pct, 2)
        result.max_drawdown_pct = round(result.max_drawdown_pct, 2)
        result.avg_rr = round(result.avg_rr, 2)

        return result

    @staticmethod
    def _candles_to_dataframe(candles: list[dict[str, Any]]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        df = pd.DataFrame(candles)
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    async def _fetch_full_history(self, symbol: str, exchange: str, timeframe: str) -> list[dict[str, Any]]:
        """Fetch max available history for backtesting."""
        from datetime import UTC, datetime, timedelta

        to_date = datetime.now(UTC)
        from_date = to_date - timedelta(days=365)
        return await self.market_data.fetch_historical(symbol, exchange, from_date, to_date, timeframe)
