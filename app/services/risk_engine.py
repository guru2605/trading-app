from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.models.audit_event import AuditEvent
from app.models.holding import Holding
from app.models.trade import Trade
from app.schemas.order import OrderPlaceRequest
from app.schemas.safety import RiskCheckResult, SafetyConfig
from app.services.safety import SafetyService


class RiskEngineService:
    def __init__(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        kite: KiteClient | None = None,
    ) -> None:
        self.db = db
        self.redis = redis
        self.kite = kite
        self.safety = SafetyService(redis)

    async def validate_order(self, req: OrderPlaceRequest) -> list[RiskCheckResult]:
        config = await self.safety.get_config()
        results: list[RiskCheckResult] = []

        stages = [
            ("safety_check", self._check_safety),
            ("margin_check", self._check_margin),
            ("exposure_check", self._check_exposure),
            ("drawdown_check", self._check_drawdown),
            ("rate_limit_check", self._check_rate_limit),
            ("duplicate_check", self._check_duplicate),
        ]

        for stage_name, check_fn in stages:
            result = await check_fn(req, config)
            results.append(RiskCheckResult(stage=stage_name, passed=result[0], reason=result[1]))

        return results

    async def _check_safety(self, req: OrderPlaceRequest, config: SafetyConfig) -> tuple[bool, str]:
        blocked, reason = await self.safety.is_blocked()
        if blocked:
            return False, reason
        return True, "Safety checks passed."

    async def _check_margin(self, req: OrderPlaceRequest, config: SafetyConfig) -> tuple[bool, str]:
        if config.dry_run or self.kite is None:
            return True, "Margin check skipped (dry_run or no Kite connection)."
        try:
            params: list[dict[str, Any]] = [
                {
                    "exchange": req.exchange,
                    "tradingsymbol": req.tradingsymbol,
                    "transaction_type": req.transaction_type,
                    "quantity": req.quantity,
                    "order_type": req.order_type,
                    "product": req.product,
                    "price": req.price or 0,
                }
            ]
            margin_data = await self.kite.order_margins(params)
            if not margin_data:
                return True, "Margin data unavailable, passing."

            required = float(margin_data[0].get("total", 0))
            margins = await self.kite.margins()
            available = float(margins.get("equity", {}).get("available", {}).get("live_balance", 0))

            buffer = required * 1.2  # 20% buffer
            if available >= buffer:
                return True, f"Margin sufficient: available={available:.2f}, required(+20%)={buffer:.2f}"
            return False, f"Insufficient margin: available={available:.2f}, required(+20%)={buffer:.2f}"
        except Exception as e:
            return True, f"Margin check error (passing): {e}"

    async def _check_exposure(self, req: OrderPlaceRequest, config: SafetyConfig) -> tuple[bool, str]:
        order_value = req.quantity * (req.price or 0)

        if req.order_type == "MARKET" and req.price is None:
            return True, "Market order without price, exposure check skipped."

        if order_value > config.max_order_value:
            return False, f"Order value {order_value:.2f} exceeds max {config.max_order_value:.2f}."

        # Check single-position concentration
        result = await self.db.execute(select(func.sum(Holding.last_price * Holding.quantity)))
        total_portfolio = result.scalar() or 0.0

        if total_portfolio > 0:
            position_pct = (order_value / (total_portfolio + order_value)) * 100
            if position_pct > config.max_position_pct:
                return False, (
                    f"Position concentration {position_pct:.1f}% exceeds max {config.max_position_pct:.1f}%."
                )

        return True, "Exposure check passed."

    async def _check_drawdown(self, req: OrderPlaceRequest, config: SafetyConfig) -> tuple[bool, str]:
        today = datetime.now(UTC).date()
        today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)

        # Sum realized P&L from today's trades
        sell_result = await self.db.execute(
            select(func.sum(Trade.price * Trade.quantity)).where(
                Trade.transaction_type == "SELL",
                Trade.created_at >= today_start,
            )
        )
        sell_value = sell_result.scalar() or 0.0

        buy_result = await self.db.execute(
            select(func.sum(Trade.price * Trade.quantity)).where(
                Trade.transaction_type == "BUY",
                Trade.created_at >= today_start,
            )
        )
        buy_value = buy_result.scalar() or 0.0

        realized_pnl = sell_value - buy_value

        if realized_pnl < 0 and abs(realized_pnl) >= config.max_daily_loss:
            return False, f"Daily loss {abs(realized_pnl):.2f} exceeds max {config.max_daily_loss:.2f}."

        return True, f"Drawdown check passed. Today's realized P&L: {realized_pnl:.2f}"

    async def _check_rate_limit(self, req: OrderPlaceRequest, config: SafetyConfig) -> tuple[bool, str]:
        today = datetime.now(UTC).date()
        today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)

        result = await self.db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.event_type == "order.placed",
                AuditEvent.created_at >= today_start,
            )
        )
        count = result.scalar() or 0

        if count >= config.max_orders_per_day:
            return False, f"Rate limit reached: {count}/{config.max_orders_per_day} orders today."

        return True, f"Rate limit OK: {count}/{config.max_orders_per_day} orders today."

    async def _check_duplicate(self, req: OrderPlaceRequest, config: SafetyConfig) -> tuple[bool, str]:
        cutoff = datetime.now(UTC) - timedelta(seconds=30)

        # Check payload for matching tradingsymbol + transaction_type
        events_result = await self.db.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "order.placed",
                AuditEvent.created_at >= cutoff,
            )
        )
        events = events_result.scalars().all()
        for event in events:
            payload = event.payload or {}
            if (
                payload.get("tradingsymbol") == req.tradingsymbol
                and payload.get("transaction_type") == req.transaction_type
            ):
                return False, (
                    f"Duplicate order detected: {req.transaction_type} {req.tradingsymbol} "
                    f"was placed in the last 30 seconds."
                )

        return True, "No duplicate orders detected."
