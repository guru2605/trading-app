from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# ── Watchlist ──


class WatchlistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tradingsymbol: str
    exchange: str
    notes: str
    added_at: datetime


class WatchlistItemCreateRequest(BaseModel):
    tradingsymbol: str
    exchange: str = "NSE"
    notes: str = ""


# ── Signals ──


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tradingsymbol: str
    exchange: str
    signal_type: str
    timeframe: str
    entry_price: float
    stop_loss: float
    target_price: float
    confidence: float
    indicators: dict[str, Any]
    rationale: str
    status: str
    created_at: datetime
    expired_at: datetime | None


class SignalUpdateRequest(BaseModel):
    status: str  # executed / expired


# ── Scanner ──


class ScanRequest(BaseModel):
    timeframe: str = "15minute"


class ScanResultItem(BaseModel):
    tradingsymbol: str
    exchange: str
    signal_type: str
    entry_price: float
    stop_loss: float
    target_price: float
    confidence: float
    rationale: str


class ScanResponse(BaseModel):
    scanned: int
    signals_generated: int
    results: list[ScanResultItem]
    errors: list[str] = []
