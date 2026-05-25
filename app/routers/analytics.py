from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class SignalQualityResponse(BaseModel):
    available: bool = False
    reason: str | None = None
    period_days: int | None = None
    total_signals: int | None = None
    wins: int | None = None
    losses: int | None = None
    win_rate: float | None = None
    avg_rr: float | None = None
    profit_factor: float | None = None
    expectancy: float | None = None
    avg_win_rr: float | None = None
    avg_loss_rr: float | None = None


@router.get("/signal-quality", response_model=SignalQualityResponse)
async def signal_quality(
    lookback_days: int = 30,
    db: AsyncSession = Depends(get_db),
) -> SignalQualityResponse:
    service = AnalyticsService(db)
    result = await service.signal_quality(lookback_days)
    return SignalQualityResponse(**result)


@router.get("/performance/timeframe")
async def performance_by_timeframe(
    lookback_days: int = 30,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    service = AnalyticsService(db)
    return await service.performance_by_timeframe(lookback_days)


@router.get("/performance/symbol")
async def performance_by_symbol(
    lookback_days: int = 30,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    service = AnalyticsService(db)
    return await service.performance_by_symbol(lookback_days, limit)


@router.get("/summary")
async def signal_summary(
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    service = AnalyticsService(db)
    return await service.signal_count_summary()
