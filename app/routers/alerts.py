from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_kite_client
from app.kite.client import KiteClient
from app.schemas.alert import (
    AlertCheckResponse,
    AlertCreateRequest,
    AlertResponse,
    AlertUpdateRequest,
)
from app.services.alert import AlertService
from app.services.audit import AuditService

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[AlertResponse]:
    service = AlertService(db)
    return await service.list_alerts(is_active=is_active)


@router.post("", response_model=AlertResponse)
async def create_alert(
    req: AlertCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    service = AlertService(db)
    alert = await service.create_alert(
        tradingsymbol=req.tradingsymbol,
        exchange=req.exchange,
        alert_type=req.alert_type,
        target_value=req.target_value,
    )
    return AlertResponse.model_validate(alert)


@router.put("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    req: AlertUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    service = AlertService(db)
    alert = await service.update_alert(
        alert_id=alert_id,
        target_value=req.target_value,
        is_active=req.is_active,
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertResponse.model_validate(alert)


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = AlertService(db)
    deleted = await service.delete_alert(alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert deleted"}


@router.post("/check", response_model=AlertCheckResponse)
async def check_alerts(
    db: AsyncSession = Depends(get_db),
    kite: KiteClient = Depends(get_kite_client),
) -> AlertCheckResponse:
    service = AlertService(db, kite)
    try:
        results = await service.check_alerts()
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    triggered_count = sum(1 for r in results if r.triggered)

    if triggered_count > 0:
        audit = AuditService(db)
        triggered_symbols = [r.tradingsymbol for r in results if r.triggered]
        await audit.log(
            "alert.triggered",
            "alert",
            payload={"triggered": triggered_symbols},
        )

    return AlertCheckResponse(
        checked=len(results),
        triggered=triggered_count,
        results=results,
    )
