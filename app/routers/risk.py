from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_redis
from app.models.audit_event import AuditEvent
from app.models.trade import Trade
from app.schemas.risk import RiskSnapshotCreateResponse, RiskSnapshotResponse
from app.schemas.safety import PanicResponse, SafetyConfig, SafetyStatusResponse
from app.services.audit import AuditService
from app.services.risk import RiskSnapshotService
from app.services.safety import SafetyService

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/snapshots", response_model=list[RiskSnapshotResponse])
async def list_snapshots(
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
) -> list[RiskSnapshotResponse]:
    service = RiskSnapshotService(db)
    return await service.list_snapshots(limit=limit)


@router.get("/snapshots/latest", response_model=RiskSnapshotResponse | None)
async def get_latest_snapshot(
    db: AsyncSession = Depends(get_db),
) -> RiskSnapshotResponse | None:
    service = RiskSnapshotService(db)
    return await service.get_latest()


@router.post("/snapshots", response_model=RiskSnapshotCreateResponse)
async def create_snapshot(
    db: AsyncSession = Depends(get_db),
) -> RiskSnapshotCreateResponse:
    service = RiskSnapshotService(db)
    snapshot = await service.create_snapshot()
    return RiskSnapshotCreateResponse(
        id=snapshot.id,
        snapshot_date=snapshot.snapshot_date,
        message="Risk snapshot created.",
    )


@router.get("/status", response_model=SafetyStatusResponse)
async def get_risk_status(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SafetyStatusResponse:
    safety = SafetyService(redis)
    config = await safety.get_config()

    today = datetime.now(UTC).date()
    today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)

    # Count today's orders
    order_count_result = await db.execute(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.event_type == "order.placed",
            AuditEvent.created_at >= today_start,
        )
    )
    orders_today = order_count_result.scalar() or 0

    # Today's realized P&L
    sell_result = await db.execute(
        select(func.sum(Trade.price * Trade.quantity)).where(
            Trade.transaction_type == "SELL",
            Trade.created_at >= today_start,
        )
    )
    buy_result = await db.execute(
        select(func.sum(Trade.price * Trade.quantity)).where(
            Trade.transaction_type == "BUY",
            Trade.created_at >= today_start,
        )
    )
    realized_pnl = (sell_result.scalar() or 0.0) - (buy_result.scalar() or 0.0)

    return SafetyStatusResponse(
        config=config,
        panic_active=config.panic_mode,
        cooldown_active=await safety.is_cooldown_active(),
        trading_hours_active=safety.is_trading_hours(),
        orders_today=orders_today,
        realized_pnl_today=round(realized_pnl, 2),
    )


@router.post("/panic", response_model=PanicResponse)
async def activate_panic(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> PanicResponse:
    safety = SafetyService(redis)
    await safety.activate_panic()

    audit = AuditService(db)
    await audit.log("safety.panic", "safety", payload={"action": "activated"})

    return PanicResponse(panic_mode=True, message="Panic mode activated. All orders blocked.")


@router.put("/config", response_model=SafetyConfig)
async def update_safety_config(
    updates: dict[str, object],
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SafetyConfig:
    safety = SafetyService(redis)
    config = await safety.update_config(updates)

    audit = AuditService(db)
    await audit.log(
        "safety.config_updated",
        "safety",
        payload={"updates": {k: str(v) for k, v in updates.items()}},
    )

    return config
