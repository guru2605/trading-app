from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.journal import (
    JournalAnalytics,
    JournalEntryCreateRequest,
    JournalEntryResponse,
    JournalEntryUpdateRequest,
)
from app.services.audit import AuditService
from app.services.journal import JournalService

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("/analytics", response_model=JournalAnalytics)
async def get_analytics(
    db: AsyncSession = Depends(get_db),
) -> JournalAnalytics:
    service = JournalService(db)
    return await service.get_analytics()


@router.get("", response_model=list[JournalEntryResponse])
async def list_entries(
    tradingsymbol: str | None = None,
    entry_type: str | None = None,
    trade_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[JournalEntryResponse]:
    service = JournalService(db)
    return await service.list_entries(
        tradingsymbol=tradingsymbol,
        entry_type=entry_type,
        trade_id=trade_id,
    )


@router.post("", response_model=JournalEntryResponse)
async def create_entry(
    req: JournalEntryCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    service = JournalService(db)
    entry = await service.create_entry(
        tradingsymbol=req.tradingsymbol,
        entry_type=req.entry_type,
        content=req.content,
        tags=req.tags,
        strategy=req.strategy,
        outcome=req.outcome,
        emotional_state=req.emotional_state,
        trade_id=req.trade_id,
    )
    audit = AuditService(db)
    await audit.log(
        "journal.created",
        "journal",
        entity_id=str(entry.id),
        payload={"tradingsymbol": entry.tradingsymbol, "entry_type": entry.entry_type},
    )
    return JournalEntryResponse.model_validate(entry)


@router.get("/{entry_id}", response_model=JournalEntryResponse)
async def get_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    service = JournalService(db)
    entry = await service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return JournalEntryResponse.model_validate(entry)


@router.put("/{entry_id}", response_model=JournalEntryResponse)
async def update_entry(
    entry_id: int,
    req: JournalEntryUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    service = JournalService(db)
    entry = await service.update_entry(
        entry_id=entry_id,
        tradingsymbol=req.tradingsymbol,
        entry_type=req.entry_type,
        content=req.content,
        tags=req.tags,
        strategy=req.strategy,
        outcome=req.outcome,
        emotional_state=req.emotional_state,
        trade_id=req.trade_id,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    audit = AuditService(db)
    await audit.log(
        "journal.updated",
        "journal",
        entity_id=str(entry.id),
        payload={"tradingsymbol": entry.tradingsymbol},
    )
    return JournalEntryResponse.model_validate(entry)


@router.delete("/{entry_id}")
async def delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = JournalService(db)
    deleted = await service.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    audit = AuditService(db)
    await audit.log(
        "journal.deleted",
        "journal",
        entity_id=str(entry_id),
    )
    return {"message": "Journal entry deleted"}
