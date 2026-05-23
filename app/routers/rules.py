from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_optional_kite_client, get_redis
from app.kite.client import KiteClient
from app.schemas.order import (
    OrderRuleCreateRequest,
    OrderRuleResponse,
    OrderRuleUpdateRequest,
)
from app.services.rule_engine import RuleEngineService

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=list[OrderRuleResponse])
async def list_rules(
    is_active: bool | None = None,
    tradingsymbol: str | None = None,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> list[OrderRuleResponse]:
    service = RuleEngineService(db, redis)
    rules = await service.list_rules(is_active=is_active, tradingsymbol=tradingsymbol)
    return [OrderRuleResponse.model_validate(r) for r in rules]


@router.post("", response_model=OrderRuleResponse)
async def create_rule(
    req: OrderRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> OrderRuleResponse:
    service = RuleEngineService(db, redis)
    rule = await service.create_rule(
        name=req.name,
        tradingsymbol=req.tradingsymbol,
        exchange=req.exchange,
        transaction_type=req.transaction_type,
        quantity=req.quantity,
        condition=req.condition,
        price=req.price,
        trigger_price=req.trigger_price,
        product=req.product,
        order_type=req.order_type,
    )
    return OrderRuleResponse.model_validate(rule)


@router.get("/{rule_id}", response_model=OrderRuleResponse)
async def get_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> OrderRuleResponse:
    service = RuleEngineService(db, redis)
    rule = await service.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return OrderRuleResponse.model_validate(rule)


@router.put("/{rule_id}", response_model=OrderRuleResponse)
async def update_rule(
    rule_id: int,
    req: OrderRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> OrderRuleResponse:
    service = RuleEngineService(db, redis)
    updates = req.model_dump(exclude_none=True)
    rule = await service.update_rule(rule_id, **updates)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return OrderRuleResponse.model_validate(rule)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, str]:
    service = RuleEngineService(db, redis)
    deleted = await service.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted"}


@router.post("/evaluate")
async def evaluate_rules(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> list[dict[str, Any]]:
    service = RuleEngineService(db, redis, kite)
    return await service.evaluate_rules()
