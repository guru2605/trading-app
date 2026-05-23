from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.behavior_flag import BehaviorFlag
from app.models.trade import Trade
from app.schemas.behavior import BehaviorFlagResponse, BehaviorSummary


class BehaviorDetectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def detect_all(self) -> list[BehaviorFlag]:
        """Run all 5 detectors and persist any new flags."""
        flags: list[BehaviorFlag] = []
        flags.extend(await self._detect_overtrading())
        flags.extend(await self._detect_revenge_trading())
        flags.extend(await self._detect_position_spike())
        flags.extend(await self._detect_loss_streak())
        flags.extend(await self._detect_averaging_down())
        return flags

    async def list_flags(
        self,
        flag_type: str | None = None,
        severity: str | None = None,
        is_acknowledged: bool | None = None,
    ) -> list[BehaviorFlagResponse]:
        query = select(BehaviorFlag).order_by(BehaviorFlag.created_at.desc())
        if flag_type is not None:
            query = query.where(BehaviorFlag.flag_type == flag_type)
        if severity is not None:
            query = query.where(BehaviorFlag.severity == severity)
        if is_acknowledged is not None:
            query = query.where(BehaviorFlag.is_acknowledged == is_acknowledged)
        result = await self.db.execute(query)
        flags = list(result.scalars().all())
        return [BehaviorFlagResponse.model_validate(f) for f in flags]

    async def acknowledge_flag(self, flag_id: int, is_acknowledged: bool) -> BehaviorFlag | None:
        result = await self.db.execute(select(BehaviorFlag).where(BehaviorFlag.id == flag_id))
        flag = result.scalar_one_or_none()
        if flag is None:
            return None
        flag.is_acknowledged = is_acknowledged
        await self.db.commit()
        await self.db.refresh(flag)
        return flag

    async def get_summary(self) -> BehaviorSummary:
        result = await self.db.execute(select(BehaviorFlag))
        all_flags = list(result.scalars().all())

        by_severity: dict[str, int] = {}
        unacknowledged = 0
        for f in all_flags:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            if not f.is_acknowledged:
                unacknowledged += 1

        recent = sorted(all_flags, key=lambda f: f.created_at, reverse=True)[:10]

        return BehaviorSummary(
            total=len(all_flags),
            by_severity=by_severity,
            unacknowledged=unacknowledged,
            recent_flags=[BehaviorFlagResponse.model_validate(f) for f in recent],
        )

    async def _detect_overtrading(self) -> list[BehaviorFlag]:
        """Flag if > 15 trades in a single day."""
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(select(func.count()).select_from(Trade).where(Trade.traded_at >= today_start))
        count = result.scalar_one()

        flags: list[BehaviorFlag] = []
        if count > 15:
            flag = BehaviorFlag(
                flag_type="overtrading",
                severity="warning",
                description=f"Executed {count} trades today (threshold: 15). Consider slowing down.",
            )
            self.db.add(flag)
            await self.db.commit()
            await self.db.refresh(flag)
            flags.append(flag)
        return flags

    async def _detect_revenge_trading(self) -> list[BehaviorFlag]:
        """Flag if a BUY occurs within 5 minutes of a losing SELL on the same symbol."""
        # Get recent SELL trades (last 24h)
        since = datetime.now(UTC) - timedelta(hours=24)
        sell_result = await self.db.execute(
            select(Trade)
            .where(Trade.transaction_type == "SELL", Trade.traded_at >= since)
            .order_by(Trade.traded_at.asc())
        )
        sells = list(sell_result.scalars().all())

        buy_result = await self.db.execute(
            select(Trade)
            .where(Trade.transaction_type == "BUY", Trade.traded_at >= since)
            .order_by(Trade.traded_at.asc())
        )
        buys = list(buy_result.scalars().all())

        flags: list[BehaviorFlag] = []
        for sell in sells:
            if sell.traded_at is None:
                continue
            # Check if this was a losing sell by finding an earlier buy at higher price
            earlier_buys = [
                b
                for b in buys
                if b.tradingsymbol == sell.tradingsymbol
                and b.traded_at is not None
                and b.traded_at < sell.traded_at
                and b.price > sell.price
            ]
            if not earlier_buys:
                continue

            # Now check for a revenge buy within 5 minutes after the losing sell
            for buy in buys:
                if buy.tradingsymbol != sell.tradingsymbol:
                    continue
                if buy.traded_at is None:
                    continue
                time_diff = (buy.traded_at - sell.traded_at).total_seconds()
                if 0 < time_diff <= 300:  # within 5 minutes
                    flag = BehaviorFlag(
                        flag_type="revenge_trade",
                        severity="critical",
                        description=(
                            f"Revenge trade detected on {sell.tradingsymbol}: "
                            f"re-entered BUY within {int(time_diff)}s of a losing SELL."
                        ),
                        trade_id=buy.id,
                    )
                    self.db.add(flag)
                    flags.append(flag)
                    break  # one flag per sell

        if flags:
            await self.db.commit()
            for f in flags:
                await self.db.refresh(f)
        return flags

    async def _detect_position_spike(self) -> list[BehaviorFlag]:
        """Flag if latest trade notional > 2x the average of last 20 trades."""
        result = await self.db.execute(select(Trade).order_by(Trade.traded_at.desc().nulls_last()).limit(21))
        trades = list(result.scalars().all())

        if len(trades) < 2:
            return []

        latest = trades[0]
        previous = trades[1:]

        if not previous:
            return []

        avg_notional = sum(t.quantity * t.price for t in previous) / len(previous)
        latest_notional = latest.quantity * latest.price

        flags: list[BehaviorFlag] = []
        if avg_notional > 0 and latest_notional > 2 * avg_notional:
            flag = BehaviorFlag(
                flag_type="position_spike",
                severity="warning",
                description=(
                    f"Position size spike on {latest.tradingsymbol}: "
                    f"notional {latest_notional:,.0f} vs avg {avg_notional:,.0f} "
                    f"({latest_notional / avg_notional:.1f}x)."
                ),
                trade_id=latest.id,
            )
            self.db.add(flag)
            await self.db.commit()
            await self.db.refresh(flag)
            flags.append(flag)
        return flags

    async def _detect_loss_streak(self) -> list[BehaviorFlag]:
        """Flag consecutive losing trades per symbol. 3+ = info, 5+ = warning."""
        result = await self.db.execute(select(Trade).order_by(Trade.tradingsymbol, Trade.traded_at.asc().nulls_last()))
        trades = list(result.scalars().all())

        # Group by symbol and look for consecutive sell losses
        symbol_trades: dict[str, list[Trade]] = {}
        for t in trades:
            symbol_trades.setdefault(t.tradingsymbol, []).append(t)

        flags: list[BehaviorFlag] = []
        for symbol, sym_trades in symbol_trades.items():
            # Build a P&L sequence: pair BUYs with subsequent SELLs
            buy_prices: list[float] = []
            consecutive_losses = 0
            max_streak = 0

            for t in sym_trades:
                if t.transaction_type == "BUY":
                    buy_prices.append(t.price)
                elif t.transaction_type == "SELL" and buy_prices:
                    buy_price = buy_prices.pop(0)
                    if t.price < buy_price:
                        consecutive_losses += 1
                        max_streak = max(max_streak, consecutive_losses)
                    else:
                        consecutive_losses = 0

            if max_streak >= 5:
                flag = BehaviorFlag(
                    flag_type="loss_streak",
                    severity="warning",
                    description=f"{symbol}: {max_streak} consecutive losing trades detected.",
                )
                self.db.add(flag)
                flags.append(flag)
            elif max_streak >= 3:
                flag = BehaviorFlag(
                    flag_type="loss_streak",
                    severity="info",
                    description=f"{symbol}: {max_streak} consecutive losing trades detected.",
                )
                self.db.add(flag)
                flags.append(flag)

        if flags:
            await self.db.commit()
            for f in flags:
                await self.db.refresh(f)
        return flags

    async def _detect_averaging_down(self) -> list[BehaviorFlag]:
        """Flag 3+ successive BUYs at lower prices on the same symbol."""
        result = await self.db.execute(
            select(Trade)
            .where(Trade.transaction_type == "BUY")
            .order_by(Trade.tradingsymbol, Trade.traded_at.asc().nulls_last())
        )
        buys = list(result.scalars().all())

        symbol_buys: dict[str, list[Trade]] = {}
        for b in buys:
            symbol_buys.setdefault(b.tradingsymbol, []).append(b)

        flags: list[BehaviorFlag] = []
        for symbol, sym_buys in symbol_buys.items():
            descending_count = 1
            max_descending = 1
            for i in range(1, len(sym_buys)):
                if sym_buys[i].price < sym_buys[i - 1].price:
                    descending_count += 1
                    max_descending = max(max_descending, descending_count)
                else:
                    descending_count = 1

            if max_descending >= 3:
                flag = BehaviorFlag(
                    flag_type="averaging_down",
                    severity="warning",
                    description=(
                        f"{symbol}: {max_descending} successive BUYs at decreasing prices. " f"Possible averaging down."
                    ),
                    trade_id=sym_buys[-1].id,
                )
                self.db.add(flag)
                flags.append(flag)

        if flags:
            await self.db.commit()
            for f in flags:
                await self.db.refresh(f)
        return flags
