from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tradingsymbol: str
    exchange: str
    alert_type: str
    target_value: float
    is_active: bool
    triggered_at: datetime | None
    created_at: datetime


class AlertCreateRequest(BaseModel):
    tradingsymbol: str
    exchange: str = "NSE"
    alert_type: str  # price_above / price_below / pct_change
    target_value: float


class AlertUpdateRequest(BaseModel):
    target_value: float | None = None
    is_active: bool | None = None


class AlertCheckResult(BaseModel):
    tradingsymbol: str
    alert_type: str
    target_value: float
    current_price: float
    triggered: bool


class AlertCheckResponse(BaseModel):
    checked: int
    triggered: int
    results: list[AlertCheckResult]
