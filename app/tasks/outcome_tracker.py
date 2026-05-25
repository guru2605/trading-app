"""Outcome tracker — evaluates active signals against current prices."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.signal import Signal
from app.services.market_data import MarketDataService

logger = logging.getLogger(__name__)

TRADING_DAYS_EXPIRY = 5
MAX_CALENDAR_DAYS = 10  # rough upper bound for 5 trading days


async def evaluate_signal_outcomes(db: AsyncSession, market_data: MarketDataService) -> int:
    """Check active signals against current prices and record outcomes.

    Returns count of signals resolved this run.
    """
    result = await db.execute(select(Signal).where(Signal.status == "active", Signal.outcome.is_(None)))
    signals = list(result.scalars().all())

    if not signals:
        return 0

    resolved = 0
    now = datetime.now(UTC)

    for signal in signals:
        try:
            candles = await market_data.fetch_historical(
                signal.tradingsymbol,
                signal.exchange,
                from_date=now - timedelta(days=1),
                to_date=now,
                interval="day",
            )
            if not candles:
                continue

            current_price = float(candles[-1]["close"])
            high_price = float(candles[-1]["high"])
            low_price = float(candles[-1]["low"])

            outcome: str | None = None
            exit_price: float | None = None

            if signal.signal_type == "BUY":
                if high_price >= signal.target_price:
                    outcome = "win"
                    exit_price = signal.target_price
                elif low_price <= signal.stop_loss:
                    outcome = "loss"
                    exit_price = signal.stop_loss
            else:  # SELL
                if low_price <= signal.target_price:
                    outcome = "win"
                    exit_price = signal.target_price
                elif high_price >= signal.stop_loss:
                    outcome = "loss"
                    exit_price = signal.stop_loss

            # Auto-expire if no outcome after MAX_CALENDAR_DAYS
            if outcome is None and signal.created_at:
                created = signal.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                days_active = (now - created).days
                if days_active >= MAX_CALENDAR_DAYS:
                    outcome = "expired"
                    exit_price = current_price

            if outcome is not None:
                signal.outcome = outcome
                signal.actual_exit_price = exit_price
                signal.outcome_at = now

                if exit_price is not None:
                    risk = abs(signal.entry_price - signal.stop_loss)
                    if risk > 0:
                        if signal.signal_type == "BUY":
                            actual_pnl = exit_price - signal.entry_price
                        else:
                            actual_pnl = signal.entry_price - exit_price
                        signal.actual_rr = round(actual_pnl / risk, 2)

                if outcome in ("loss", "expired"):
                    signal.status = "expired"
                    signal.expired_at = now

                resolved += 1

        except Exception:
            logger.debug("Failed to evaluate outcome for %s", signal.tradingsymbol)

    if resolved > 0:
        await db.commit()

    return resolved


async def outcome_tracker_loop() -> None:
    """Run outcome evaluation every 15 minutes during market hours (IST 9:15-15:30)."""
    market_data = MarketDataService()

    while True:
        try:
            now_utc = datetime.now(UTC)
            # IST = UTC + 5:30
            ist_hour = (now_utc.hour + 5) % 24 + (1 if now_utc.minute >= 30 else 0)
            ist_minute = (now_utc.minute + 30) % 60

            is_market_hours = (
                (ist_hour > 9 or (ist_hour == 9 and ist_minute >= 15))
                and (ist_hour < 15 or (ist_hour == 15 and ist_minute <= 30))
                and now_utc.weekday() < 5  # Mon-Fri
            )

            if is_market_hours:
                async with async_session() as db:
                    resolved = await evaluate_signal_outcomes(db, market_data)
                    if resolved > 0:
                        logger.info("Outcome tracker: resolved %d signals", resolved)

        except Exception:
            logger.exception("Outcome tracker error")

        await asyncio.sleep(900)  # 15 minutes
