from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.tax import (
    DailyTaxEstimate,
    TaxComputeResponse,
    TaxLotResponse,
    TaxSummaryResponse,
    WashSaleResponse,
)
from app.services.audit import AuditService
from app.services.tax import TaxService

router = APIRouter(prefix="/api/tax", tags=["tax"])


@router.get("/summary", response_model=TaxSummaryResponse)
async def get_tax_summary(
    fy: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> TaxSummaryResponse:
    service = TaxService(db)
    return await service.get_summary(fy)


@router.get("/lots", response_model=list[TaxLotResponse])
async def get_tax_lots(
    fy: str | None = None,
    tradingsymbol: str | None = None,
    holding_type: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[TaxLotResponse]:
    service = TaxService(db)
    return await service.get_lots(fy=fy, tradingsymbol=tradingsymbol, holding_type=holding_type)


@router.get("/wash-sales", response_model=list[WashSaleResponse])
async def get_wash_sales(
    fy: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[WashSaleResponse]:
    service = TaxService(db)
    return await service.detect_wash_sales(fy)


@router.get("/daily", response_model=list[DailyTaxEstimate])
async def get_daily_estimate(
    fy: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[DailyTaxEstimate]:
    service = TaxService(db)
    return await service.get_daily_estimate(fy)


@router.get("/report/download")
async def download_tax_report(
    fy: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    service = TaxService(db)
    csv_content = await service.generate_csv(fy)

    audit = AuditService(db)
    await audit.log("tax.report.downloaded", "tax_lot", payload={"fy": fy})

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tax_report_{fy or 'current'}.csv"},
    )


@router.post("/compute", response_model=TaxComputeResponse)
async def compute_tax_lots(
    fy: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> TaxComputeResponse:
    service = TaxService(db)
    result = await service.compute_tax_lots(fy)

    audit = AuditService(db)
    await audit.log(
        "tax.lots.computed",
        "tax_lot",
        payload={"fy": fy, "lots_created": result.lots_created, "lots_updated": result.lots_updated},
    )

    return result
