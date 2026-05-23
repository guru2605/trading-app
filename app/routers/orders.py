from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_optional_kite_client, get_redis
from app.kite.client import KiteClient
from app.schemas.order import (
    OrderMarginResponse,
    OrderPlaceRequest,
    OrderPlaceResponse,
)
from app.services.order import OrderService

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("/place", response_model=OrderPlaceResponse)
async def place_order(
    req: OrderPlaceRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> OrderPlaceResponse:
    service = OrderService(db, redis, kite)
    return await service.place_order(req)


@router.delete("/{order_id}")
async def cancel_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> dict[str, Any]:
    service = OrderService(db, redis, kite)
    return await service.cancel_order(order_id)


@router.post("/margins", response_model=OrderMarginResponse)
async def check_margins(
    req: OrderPlaceRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> OrderMarginResponse:
    service = OrderService(db, redis, kite)
    return await service.get_order_margins(req)
