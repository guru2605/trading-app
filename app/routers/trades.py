from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_kite_client
from app.kite.client import KiteClient
from app.schemas.trade import TradeResponse, TradeSyncResponse
from app.services.audit import AuditService
from app.services.trade import TradeService

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("", response_model=list[TradeResponse])
async def get_trades(
    tradingsymbol: str | None = None,
    transaction_type: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[TradeResponse]:
    service = TradeService(db)
    return await service.get_trades(
        tradingsymbol=tradingsymbol,
        transaction_type=transaction_type,
        limit=limit,
    )


@router.post("/sync", response_model=TradeSyncResponse)
async def sync_trades(
    db: AsyncSession = Depends(get_db),
    kite: KiteClient = Depends(get_kite_client),
) -> TradeSyncResponse:
    service = TradeService(db, kite)
    try:
        count = await service.sync_trades()
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    audit = AuditService(db)
    await audit.log("trade.synced", "trade", payload={"synced": count})

    return TradeSyncResponse(synced=count, message=f"Synced {count} new trades from Kite.")
