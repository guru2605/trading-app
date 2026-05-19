from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HoldingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tradingsymbol: str
    exchange: str
    isin: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    day_change: float
    day_change_pct: float
    weight: float = 0.0
    synced_at: datetime


class PositionResponse(BaseModel):
    tradingsymbol: str
    exchange: str
    product: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    day_buy_quantity: int = 0
    day_sell_quantity: int = 0
    buy_value: float = 0.0
    sell_value: float = 0.0


class OrderResponse(BaseModel):
    order_id: str
    tradingsymbol: str
    exchange: str
    transaction_type: str
    order_type: str
    product: str
    quantity: int
    price: float
    trigger_price: float = 0.0
    status: str
    filled_quantity: int = 0
    average_price: float = 0.0
    order_timestamp: str | None = None


class PortfolioSummary(BaseModel):
    total_invested: float
    total_current: float
    total_pnl: float
    total_pnl_pct: float
    day_pnl: float
    day_pnl_pct: float
    holdings_count: int


class AllocationItem(BaseModel):
    sector: str
    value: float
    weight: float
    holdings_count: int


class AllocationResponse(BaseModel):
    allocations: list[AllocationItem]
    total_value: float


class CorrelationPair(BaseModel):
    stock_a: str
    stock_b: str
    correlation: float


class CorrelationResponse(BaseModel):
    symbols: list[str]
    matrix: list[list[float]]
    high_correlations: list[CorrelationPair]
    warnings: list[str]


class ExposureResponse(BaseModel):
    total_exposure: float
    net_exposure: float
    long_exposure: float
    short_exposure: float
    leverage: float
    directional_bias: str


class SyncResponse(BaseModel):
    synced: int
    message: str
