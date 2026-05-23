import json
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kite.client import KiteClient
from app.models.order_rule import OrderRule
from app.models.trade import Trade
from app.schemas.order import OrderPlaceRequest, OrderPlaceResponse
from app.services.order import OrderService


class RuleEngineService:
    def __init__(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        kite: KiteClient | None = None,
    ) -> None:
        self.db = db
        self.redis = redis
        self.kite = kite

    async def list_rules(
        self,
        is_active: bool | None = None,
        tradingsymbol: str | None = None,
    ) -> list[OrderRule]:
        query = select(OrderRule).order_by(OrderRule.created_at.desc())
        if is_active is not None:
            query = query.where(OrderRule.is_active == is_active)
        if tradingsymbol:
            query = query.where(OrderRule.tradingsymbol == tradingsymbol)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_rule(self, rule_id: int) -> OrderRule | None:
        result = await self.db.execute(select(OrderRule).where(OrderRule.id == rule_id))
        return result.scalar_one_or_none()

    async def create_rule(
        self,
        name: str,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        condition: str,
        price: float | None = None,
        trigger_price: float | None = None,
        product: str = "CNC",
        order_type: str = "MARKET",
    ) -> OrderRule:
        rule = OrderRule(
            name=name,
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            product=product,
            order_type=order_type,
            condition=condition,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def update_rule(self, rule_id: int, **updates: Any) -> OrderRule | None:
        rule = await self.get_rule(rule_id)
        if rule is None:
            return None
        for key, value in updates.items():
            if value is not None and hasattr(rule, key):
                setattr(rule, key, value)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        rule = await self.get_rule(rule_id)
        if rule is None:
            return False
        await self.db.delete(rule)
        await self.db.commit()
        return True

    async def evaluate_rules(self) -> list[dict[str, Any]]:
        rules = await self.list_rules(is_active=True)
        results: list[dict[str, Any]] = []

        for rule in rules:
            try:
                current_price = await self._get_latest_price(rule.tradingsymbol, rule.exchange)
                if current_price is None:
                    results.append(
                        {
                            "rule_id": rule.id,
                            "name": rule.name,
                            "triggered": False,
                            "reason": "No price data available.",
                        }
                    )
                    continue

                condition = self._parse_condition(rule.condition)
                triggered = self._evaluate_condition(condition, current_price)

                if triggered:
                    order_result = await self._execute_rule(rule)
                    rule.last_triggered_at = datetime.now(UTC)
                    rule.is_active = False  # One-shot: deactivate after trigger
                    await self.db.commit()
                    results.append(
                        {
                            "rule_id": rule.id,
                            "name": rule.name,
                            "triggered": True,
                            "current_price": current_price,
                            "order_status": order_result.status,
                        }
                    )
                else:
                    results.append(
                        {
                            "rule_id": rule.id,
                            "name": rule.name,
                            "triggered": False,
                            "current_price": current_price,
                            "reason": "Condition not met.",
                        }
                    )
            except Exception as e:
                results.append(
                    {
                        "rule_id": rule.id,
                        "name": rule.name,
                        "triggered": False,
                        "reason": f"Error: {e}",
                    }
                )

        return results

    async def _get_latest_price(self, tradingsymbol: str, exchange: str) -> float | None:
        # Try Kite LTP first
        if self.kite is not None:
            try:
                instrument = f"{exchange}:{tradingsymbol}"
                ltp_data = await self.kite.ltp([instrument])
                if instrument in ltp_data:
                    return float(ltp_data[instrument]["last_price"])
            except Exception:
                pass

        # Fallback: latest trade price from DB
        result = await self.db.execute(
            select(Trade.price).where(Trade.tradingsymbol == tradingsymbol).order_by(Trade.created_at.desc()).limit(1)
        )
        price = result.scalar_one_or_none()
        return float(price) if price is not None else None

    @staticmethod
    def _parse_condition(condition_str: str) -> dict[str, Any]:
        if not condition_str:
            return {}
        try:
            return json.loads(condition_str)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _evaluate_condition(condition: dict[str, Any], current_price: float) -> bool:
        cond_type = condition.get("type")
        value = condition.get("value")

        if cond_type is None or value is None:
            return False

        value = float(value)

        if cond_type == "price_above":
            return current_price > value
        if cond_type == "price_below":
            return current_price < value
        if cond_type == "price_drop_pct":
            reference = condition.get("reference_price")
            if reference is None:
                return False
            reference = float(reference)
            if reference == 0:
                return False
            drop_pct = ((reference - current_price) / reference) * 100
            return drop_pct >= value

        return False

    async def _execute_rule(self, rule: OrderRule) -> OrderPlaceResponse:
        order_service = OrderService(self.db, self.redis, self.kite)
        req = OrderPlaceRequest(
            tradingsymbol=rule.tradingsymbol,
            exchange=rule.exchange,
            transaction_type=rule.transaction_type,
            quantity=rule.quantity,
            price=rule.price,
            product=rule.product,
            order_type=rule.order_type,
            trigger_price=rule.trigger_price,
        )
        return await order_service.place_order(req)
