from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.audit import AuditEventListResponse, AuditEventResponse
from app.services.audit import AuditService

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/events", response_model=AuditEventListResponse)
async def list_audit_events(
    event_type: str | None = Query(None),
    entity_type: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AuditEventListResponse:
    service = AuditService(db)
    events, total = await service.list_events(
        event_type=event_type,
        entity_type=entity_type,
        source=source,
        limit=limit,
        offset=offset,
    )
    return AuditEventListResponse(
        events=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/events/{event_id}", response_model=AuditEventResponse)
async def get_audit_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
) -> AuditEventResponse:
    service = AuditService(db)
    event = await service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return AuditEventResponse.model_validate(event)
