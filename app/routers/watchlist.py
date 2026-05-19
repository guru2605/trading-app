from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.instrument import Instrument
from app.schemas.scanner import WatchlistItemCreateRequest, WatchlistItemResponse
from app.services.watchlist import WatchlistService

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemResponse])
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
) -> list[WatchlistItemResponse]:
    service = WatchlistService(db)
    return await service.list_items()


@router.post("", response_model=WatchlistItemResponse)
async def add_to_watchlist(
    req: WatchlistItemCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemResponse:
    service = WatchlistService(db)
    item = await service.add_item(
        tradingsymbol=req.tradingsymbol,
        exchange=req.exchange,
        notes=req.notes,
    )
    return WatchlistItemResponse.model_validate(item)


@router.delete("/{item_id}")
async def remove_from_watchlist(
    item_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = WatchlistService(db)
    deleted = await service.delete_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return {"message": "Removed from watchlist"}


@router.post("/import-holdings")
async def import_from_holdings(
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    service = WatchlistService(db)
    added = await service.import_from_holdings()
    return {"added": added, "message": f"Imported {added} symbol(s) from holdings."}


@router.get("/search-instruments")
async def search_instruments(
    q: str,
    exchange: str = "NSE",
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    """Search instruments by tradingsymbol prefix for autocomplete."""
    if len(q) < 2:
        return []
    query = (
        select(Instrument.tradingsymbol, Instrument.name, Instrument.exchange)
        .where(
            Instrument.tradingsymbol.ilike(f"{q}%"),
            Instrument.exchange == exchange.upper(),
            Instrument.instrument_type == "EQ",
        )
        .order_by(Instrument.tradingsymbol)
        .limit(20)
    )
    result = await db.execute(query)
    return [
        {"tradingsymbol": row.tradingsymbol, "name": row.name, "exchange": row.exchange}
        for row in result.all()
    ]
