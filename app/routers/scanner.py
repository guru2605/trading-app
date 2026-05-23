from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_optional_kite_client
from app.kite.client import KiteClient
from app.schemas.scanner import ScanRequest, ScanResponse, SignalResponse, SignalUpdateRequest
from app.services.audit import AuditService
from app.services.scanner import ScannerService

router = APIRouter(prefix="/api", tags=["scanner"])


@router.post("/scanner/scan", response_model=ScanResponse)
async def run_scan(
    req: ScanRequest,
    db: AsyncSession = Depends(get_db),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> ScanResponse:
    service = ScannerService(db, kite)
    results, errors = await service.scan_watchlist(timeframe=req.timeframe)

    audit = AuditService(db)
    await audit.log(
        event_type="scanner.scan",
        entity_type="scanner",
        payload={
            "timeframe": req.timeframe,
            "scanned": len(results),
            "signals": [r.tradingsymbol for r in results],
            "errors": errors,
        },
    )

    return ScanResponse(
        scanned=len(results),
        signals_generated=len(results),
        results=results,
        errors=errors,
    )


@router.get("/signals", response_model=list[SignalResponse])
async def list_signals(
    status: str | None = None,
    signal_type: str | None = None,
    tradingsymbol: str | None = None,
    db: AsyncSession = Depends(get_db),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> list[SignalResponse]:
    service = ScannerService(db, kite)
    return await service.list_signals(status=status, signal_type=signal_type, tradingsymbol=tradingsymbol)


@router.get("/signals/{signal_id}", response_model=SignalResponse)
async def get_signal(
    signal_id: int,
    db: AsyncSession = Depends(get_db),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> SignalResponse:
    service = ScannerService(db, kite)
    signal = await service.get_signal(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return SignalResponse.model_validate(signal)


@router.put("/signals/{signal_id}", response_model=SignalResponse)
async def update_signal(
    signal_id: int,
    req: SignalUpdateRequest,
    db: AsyncSession = Depends(get_db),
    kite: KiteClient | None = Depends(get_optional_kite_client),
) -> SignalResponse:
    service = ScannerService(db, kite)
    signal = await service.update_signal_status(signal_id, req.status)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return SignalResponse.model_validate(signal)
