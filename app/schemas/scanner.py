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
    outcome: str | None = None
    actual_exit_price: float | None = None
    actual_rr: float | None = None
    outcome_at: datetime | None = None


class SignalUpdateRequest(BaseModel):
    status: str  # executed / expired


class ExpireAllRequest(BaseModel):
    tradingsymbols: list[str] | None = None  # if provided, only expire these


class ExpireAllResponse(BaseModel):
    expired: int


# ── Scanner ──


class SymbolInput(BaseModel):
    tradingsymbol: str
    exchange: str = "NSE"


class ScanRequest(BaseModel):
    timeframe: str = "15minute"
    symbols: list[SymbolInput] | None = None


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


class ScanStatusResponse(BaseModel):
    last_scan: str | None = None
    status: str | None = None
    symbols_scanned: int = 0
    signals_generated: int = 0
    errors_count: int = 0
    duration_seconds: float = 0.0
