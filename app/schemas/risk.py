from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RiskSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    snapshot_date: str
    total_invested: float
    total_current: float
    total_pnl: float
    day_pnl: float
    max_single_stock_pct: float
    sector_concentration: dict[str, Any]
    details: dict[str, Any]
    created_at: datetime


class RiskSnapshotCreateResponse(BaseModel):
    id: int
    snapshot_date: str
    message: str
