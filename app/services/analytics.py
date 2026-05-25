"""Analytics service — computes signal quality metrics from outcome data.

Requires outcome tracking (Task 2.1) to populate signal outcomes.
Provides: win rate, avg R:R, profit factor, expectancy by indicator/timeframe/symbol.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Computes signal quality metrics from historical outcomes."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def signal_quality(self, lookback_days: int = 30) -> dict[str, Any]:
        """Compute overall signal quality metrics."""
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        result = await self.db.execute(
            select(Signal).where(
                Signal.outcome.in_(["win", "loss"]),
                Signal.created_at >= cutoff,
            )
        )
        signals = list(result.scalars().all())

        if not signals:
            return {"available": False, "reason": "No resolved signals in period"}

        wins = [s for s in signals if s.outcome == "win"]
        losses = [s for s in signals if s.outcome == "loss"]

        win_rate = len(wins) / len(signals) * 100 if signals else 0.0

        rr_values = [s.actual_rr for s in signals if s.actual_rr is not None]
        avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0.0

        # Profit factor
        gross_profit = sum(s.actual_rr for s in wins if s.actual_rr is not None and s.actual_rr > 0)
        gross_loss = abs(sum(s.actual_rr for s in losses if s.actual_rr is not None and s.actual_rr < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        # Expectancy
        avg_win = sum(s.actual_rr for s in wins if s.actual_rr is not None) / len(wins) if wins else 0.0
        avg_loss = sum(s.actual_rr for s in losses if s.actual_rr is not None) / len(losses) if losses else 0.0
        win_pct = len(wins) / len(signals) if signals else 0.0
        loss_pct = len(losses) / len(signals) if signals else 0.0
        expectancy = (win_pct * avg_win) + (loss_pct * avg_loss)

        return {
            "available": True,
            "period_days": lookback_days,
            "total_signals": len(signals),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "avg_rr": round(avg_rr, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
            "expectancy": round(expectancy, 4),
            "avg_win_rr": round(avg_win, 2),
            "avg_loss_rr": round(avg_loss, 2),
        }

    async def performance_by_timeframe(self, lookback_days: int = 30) -> dict[str, Any]:
        """Break down signal performance by timeframe."""
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        result = await self.db.execute(
            select(Signal).where(
                Signal.outcome.in_(["win", "loss"]),
                Signal.created_at >= cutoff,
            )
        )
        signals = list(result.scalars().all())

        breakdown: dict[str, dict[str, Any]] = {}
        for signal in signals:
            tf = signal.timeframe or "unknown"
            if tf not in breakdown:
                breakdown[tf] = {"wins": 0, "losses": 0, "total": 0, "rr_sum": 0.0}
            breakdown[tf]["total"] += 1
            if signal.outcome == "win":
                breakdown[tf]["wins"] += 1
            else:
                breakdown[tf]["losses"] += 1
            if signal.actual_rr is not None:
                breakdown[tf]["rr_sum"] += signal.actual_rr

        result_dict: dict[str, Any] = {}
        for tf, data in breakdown.items():
            total = data["total"]
            result_dict[tf] = {
                "total": total,
                "wins": data["wins"],
                "losses": data["losses"],
                "win_rate": round(data["wins"] / total * 100, 1) if total > 0 else 0.0,
                "avg_rr": round(data["rr_sum"] / total, 2) if total > 0 else 0.0,
            }

        return {"available": True, "breakdown": result_dict}

    async def performance_by_symbol(self, lookback_days: int = 30, limit: int = 20) -> dict[str, Any]:
        """Break down signal performance by symbol, sorted by win rate."""
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        result = await self.db.execute(
            select(Signal).where(
                Signal.outcome.in_(["win", "loss"]),
                Signal.created_at >= cutoff,
            )
        )
        signals = list(result.scalars().all())

        breakdown: dict[str, dict[str, Any]] = {}
        for signal in signals:
            sym = signal.tradingsymbol
            if sym not in breakdown:
                breakdown[sym] = {"wins": 0, "losses": 0, "total": 0}
            breakdown[sym]["total"] += 1
            if signal.outcome == "win":
                breakdown[sym]["wins"] += 1
            else:
                breakdown[sym]["losses"] += 1

        symbol_stats = []
        for sym, data in breakdown.items():
            total = data["total"]
            symbol_stats.append(
                {
                    "symbol": sym,
                    "total": total,
                    "wins": data["wins"],
                    "losses": data["losses"],
                    "win_rate": round(data["wins"] / total * 100, 1) if total > 0 else 0.0,
                }
            )

        symbol_stats.sort(key=lambda x: (-x["win_rate"], -x["total"]))

        return {"available": True, "symbols": symbol_stats[:limit]}

    async def signal_count_summary(self) -> dict[str, Any]:
        """Quick summary of signal counts by status."""
        result = await self.db.execute(select(Signal.status, func.count(Signal.id)).group_by(Signal.status))
        counts = {row[0]: row[1] for row in result.all()}

        return {
            "active": counts.get("active", 0),
            "expired": counts.get("expired", 0),
            "resolved_win": 0,  # Needs outcome data
            "resolved_loss": 0,
            "total": sum(counts.values()),
        }
