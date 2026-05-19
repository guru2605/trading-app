import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_kite_client, get_optional_kite_client
from app.kite.client import KiteClient
from app.models.instrument import Instrument
from app.schemas.portfolio import (
    AllocationResponse,
    CorrelationResponse,
    ExposureResponse,
    HoldingResponse,
    OrderResponse,
    PortfolioSummary,
    PositionResponse,
    SyncResponse,
)
from app.services.correlation import CorrelationService
from app.services.portfolio import PortfolioService
from app.tasks.sync_instruments import sync_instruments

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/holdings", response_model=list[HoldingResponse])
async def get_holdings(
    db: AsyncSession = Depends(get_db),
) -> list[HoldingResponse]:
    service = PortfolioService(db)
    return await service.get_holdings()


@router.get("/positions", response_model=list[PositionResponse])
async def get_positions(
    kite: KiteClient = Depends(get_kite_client),
) -> list[PositionResponse]:
    positions_data = await kite.positions()
    net = positions_data.get("net", [])
    return [
        PositionResponse(
            tradingsymbol=p.get("tradingsymbol", ""),
            exchange=p.get("exchange", ""),
            product=p.get("product", ""),
            quantity=p.get("quantity", 0),
            average_price=p.get("average_price", 0.0),
            last_price=p.get("last_price", 0.0),
            pnl=p.get("pnl", 0.0),
            day_buy_quantity=p.get("day_buy_quantity", 0),
            day_sell_quantity=p.get("day_sell_quantity", 0),
            buy_value=p.get("buy_value", 0.0),
            sell_value=p.get("sell_value", 0.0),
        )
        for p in net
    ]


@router.get("/orders", response_model=list[OrderResponse])
async def get_orders(
    kite: KiteClient = Depends(get_kite_client),
) -> list[OrderResponse]:
    orders = await kite.orders()
    return [
        OrderResponse(
            order_id=o.get("order_id", ""),
            tradingsymbol=o.get("tradingsymbol", ""),
            exchange=o.get("exchange", ""),
            transaction_type=o.get("transaction_type", ""),
            order_type=o.get("order_type", ""),
            product=o.get("product", ""),
            quantity=o.get("quantity", 0),
            price=o.get("price", 0.0),
            trigger_price=o.get("trigger_price", 0.0),
            status=o.get("status", ""),
            filled_quantity=o.get("filled_quantity", 0),
            average_price=o.get("average_price", 0.0),
            order_timestamp=str(o["order_timestamp"]) if o.get("order_timestamp") else None,
        )
        for o in orders
    ]


@router.get("/summary", response_model=PortfolioSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
) -> PortfolioSummary:
    service = PortfolioService(db)
    return await service.get_summary()


@router.get("/allocation", response_model=AllocationResponse)
async def get_allocation(
    db: AsyncSession = Depends(get_db),
) -> AllocationResponse:
    service = PortfolioService(db)
    return await service.get_allocation()


@router.get("/correlation", response_model=CorrelationResponse)
async def get_correlation(
    db: AsyncSession = Depends(get_db),
    kite: KiteClient = Depends(get_kite_client),
) -> CorrelationResponse:
    service = CorrelationService(db, kite)
    return await service.compute_correlation()


@router.get("/exposure", response_model=ExposureResponse)
async def get_exposure(
    db: AsyncSession = Depends(get_db),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> ExposureResponse:
    service = PortfolioService(db, kite)
    data = await service.get_exposure()
    return ExposureResponse(**data)


@router.post("/sync", response_model=SyncResponse)
async def sync_holdings(
    db: AsyncSession = Depends(get_db),
    kite: KiteClient = Depends(get_kite_client),
) -> SyncResponse:
    service = PortfolioService(db, kite)
    try:
        count = await service.sync_holdings()
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    # Auto-sync instruments if the table is empty
    result = await db.execute(select(func.count()).select_from(Instrument))
    inst_count = result.scalar_one()
    inst_msg = ""
    if inst_count == 0:
        try:
            synced = await sync_instruments(db)
            inst_msg = f" Also synced {synced} instruments."
        except Exception:
            logger.warning("Auto instrument sync failed", exc_info=True)

    return SyncResponse(synced=count, message=f"Synced {count} holdings from Kite.{inst_msg}")


@router.post("/sync-instruments")
async def sync_instruments_endpoint(
    db: AsyncSession = Depends(get_db),
    kite: KiteClient = Depends(get_kite_client),  # noqa: ARG001
) -> dict[str, str | int]:
    try:
        count = await sync_instruments(db)
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    return {"synced": count, "message": f"Synced {count} instruments from Kite."}
