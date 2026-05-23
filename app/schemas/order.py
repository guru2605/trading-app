from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.safety import RiskCheckResult


class OrderPlaceRequest(BaseModel):
    tradingsymbol: str
    exchange: str = "NSE"
    transaction_type: str  # BUY / SELL
    quantity: int
    price: float | None = None
    product: str = "CNC"  # CNC / MIS / NRML
    order_type: str = "MARKET"  # MARKET / LIMIT / SL / SL-M
    trigger_price: float | None = None


class OrderPlaceResponse(BaseModel):
    order_id: str | None = None
    status: str
    dry_run: bool
    risk_checks: list[RiskCheckResult]


class OrderMarginRequest(BaseModel):
    tradingsymbol: str
    exchange: str = "NSE"
    transaction_type: str
    quantity: int
    price: float | None = None
    product: str = "CNC"
    order_type: str = "MARKET"


class OrderMarginResponse(BaseModel):
    total: float
    available: float | None = None
    sufficient: bool


class OrderRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tradingsymbol: str
    exchange: str
    transaction_type: str
    quantity: int
    price: float | None
    trigger_price: float | None
    product: str
    order_type: str
    condition: str
    is_active: bool
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OrderRuleCreateRequest(BaseModel):
    name: str
    tradingsymbol: str
    exchange: str = "NSE"
    transaction_type: str = "BUY"
    quantity: int = 1
    price: float | None = None
    trigger_price: float | None = None
    product: str = "CNC"
    order_type: str = "MARKET"
    condition: str = ""  # JSON condition expression


class OrderRuleUpdateRequest(BaseModel):
    name: str | None = None
    quantity: int | None = None
    price: float | None = None
    trigger_price: float | None = None
    product: str | None = None
    order_type: str | None = None
    condition: str | None = None
    is_active: bool | None = None
