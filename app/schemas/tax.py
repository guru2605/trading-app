from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TaxLotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tradingsymbol: str
    exchange: str
    buy_date: datetime
    buy_price: float
    quantity: int
    remaining_quantity: int
    sell_date: datetime | None
    sell_price: float | None
    realized_pnl: float | None
    holding_type: str
    created_at: datetime


class TaxSummaryResponse(BaseModel):
    total_stcg: float
    total_ltcg: float
    total_intraday: float
    total_fno: float
    estimated_stcg_tax: float
    estimated_ltcg_tax: float
    fy: str


class DailyTaxEstimate(BaseModel):
    date: date
    stcg_to_date: float
    ltcg_to_date: float
    intraday_to_date: float
    fno_to_date: float
    estimated_tax: float
    advance_tax_due: float


class WashSaleResponse(BaseModel):
    tradingsymbol: str
    sell_date: datetime
    sell_price: float
    rebuy_date: datetime
    rebuy_price: float
    loss_amount: float


class TaxComputeResponse(BaseModel):
    lots_created: int
    lots_updated: int
    message: str
