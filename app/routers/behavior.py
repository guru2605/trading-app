from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.behavior import (
    BehaviorAcknowledgeRequest,
    BehaviorDetectionResponse,
    BehaviorFlagResponse,
    BehaviorSummary,
)
from app.services.audit import AuditService
from app.services.behavior import BehaviorDetectionService

router = APIRouter(prefix="/api/behavior", tags=["behavior"])


@router.post("/detect", response_model=BehaviorDetectionResponse)
async def run_detection(
    db: AsyncSession = Depends(get_db),
) -> BehaviorDetectionResponse:
    service = BehaviorDetectionService(db)
    flags = await service.detect_all()

    if flags:
        audit = AuditService(db)
        await audit.log(
            "behavior.detected",
            "behavior",
            payload={
                "count": len(flags),
                "types": [f.flag_type for f in flags],
            },
        )

    flag_responses = [BehaviorFlagResponse.model_validate(f) for f in flags]
    summary = f"Detected {len(flags)} behavioral flag(s)." if flags else "No behavioral issues detected."
    return BehaviorDetectionResponse(flags=flag_responses, summary=summary)


@router.get("/flags", response_model=list[BehaviorFlagResponse])
async def list_flags(
    flag_type: str | None = None,
    severity: str | None = None,
    is_acknowledged: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[BehaviorFlagResponse]:
    service = BehaviorDetectionService(db)
    return await service.list_flags(
        flag_type=flag_type,
        severity=severity,
        is_acknowledged=is_acknowledged,
    )


@router.get("/summary", response_model=BehaviorSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
) -> BehaviorSummary:
    service = BehaviorDetectionService(db)
    return await service.get_summary()


@router.put("/flags/{flag_id}/acknowledge", response_model=BehaviorFlagResponse)
async def acknowledge_flag(
    flag_id: int,
    req: BehaviorAcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
) -> BehaviorFlagResponse:
    service = BehaviorDetectionService(db)
    flag = await service.acknowledge_flag(flag_id, req.is_acknowledged)
    if flag is None:
        raise HTTPException(status_code=404, detail="Behavior flag not found")

    audit = AuditService(db)
    await audit.log(
        "behavior.acknowledged",
        "behavior",
        entity_id=str(flag.id),
        payload={"flag_type": flag.flag_type, "is_acknowledged": flag.is_acknowledged},
    )
    return BehaviorFlagResponse.model_validate(flag)
