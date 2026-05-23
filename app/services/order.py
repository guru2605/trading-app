from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.schemas.order import OrderMarginResponse, OrderPlaceRequest, OrderPlaceResponse
from app.services.audit import AuditService
from app.services.risk_engine import RiskEngineService
from app.services.safety import SafetyService


class OrderService:
    def __init__(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        kite: KiteClient | None = None,
    ) -> None:
        self.db = db
        self.redis = redis
        self.kite = kite
        self.risk_engine = RiskEngineService(db, redis, kite)
        self.safety = SafetyService(redis)
        self.audit = AuditService(db)

    async def place_order(self, req: OrderPlaceRequest) -> OrderPlaceResponse:
        config = await self.safety.get_config()
        risk_checks = await self.risk_engine.validate_order(req)
        all_passed = all(r.passed for r in risk_checks)

        if not all_passed:
            await self.audit.log(
                "order.blocked",
                "order",
                payload={
                    "tradingsymbol": req.tradingsymbol,
                    "transaction_type": req.transaction_type,
                    "quantity": req.quantity,
                    "reasons": [r.reason for r in risk_checks if not r.passed],
                },
            )
            return OrderPlaceResponse(
                order_id=None,
                status="BLOCKED",
                dry_run=config.dry_run,
                risk_checks=risk_checks,
            )

        if config.dry_run:
            await self.audit.log(
                "order.placed",
                "order",
                payload={
                    "tradingsymbol": req.tradingsymbol,
                    "transaction_type": req.transaction_type,
                    "quantity": req.quantity,
                    "price": req.price,
                    "dry_run": True,
                },
            )
            return OrderPlaceResponse(
                order_id="DRY_RUN",
                status="SUCCESS",
                dry_run=True,
                risk_checks=risk_checks,
            )

        if self.kite is None:
            return OrderPlaceResponse(
                order_id=None,
                status="ERROR",
                dry_run=False,
                risk_checks=risk_checks,
            )

        order_id = await self.kite.place_order(
            variety="regular",
            exchange=req.exchange,
            tradingsymbol=req.tradingsymbol,
            transaction_type=req.transaction_type,
            quantity=req.quantity,
            product=req.product,
            order_type=req.order_type,
            price=req.price,
            trigger_price=req.trigger_price,
        )

        await self.audit.log(
            "order.placed",
            "order",
            entity_id=order_id,
            payload={
                "tradingsymbol": req.tradingsymbol,
                "transaction_type": req.transaction_type,
                "quantity": req.quantity,
                "price": req.price,
                "dry_run": False,
            },
        )

        return OrderPlaceResponse(
            order_id=order_id,
            status="SUCCESS",
            dry_run=False,
            risk_checks=risk_checks,
        )

    async def cancel_order(self, order_id: str) -> dict[str, str]:
        if self.kite is None:
            return {"status": "ERROR", "message": "Kite not connected"}

        result = await self.kite.cancel_order("regular", order_id)
        await self.audit.log(
            "order.cancelled",
            "order",
            entity_id=order_id,
            payload={"result": result},
        )
        return {"status": "SUCCESS", "message": f"Order {order_id} cancelled."}

    async def get_order_margins(self, req: OrderPlaceRequest) -> OrderMarginResponse:
        if self.kite is None:
            return OrderMarginResponse(total=0, available=None, sufficient=False)

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
            total = float(margin_data[0].get("total", 0)) if margin_data else 0

            margins = await self.kite.margins()
            available = float(margins.get("equity", {}).get("available", {}).get("live_balance", 0))

            return OrderMarginResponse(
                total=total,
                available=available,
                sufficient=available >= total,
            )
        except Exception:
            return OrderMarginResponse(total=0, available=None, sufficient=False)
