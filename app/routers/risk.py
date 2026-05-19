from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.risk import RiskSnapshotCreateResponse, RiskSnapshotResponse
from app.services.risk import RiskSnapshotService

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
