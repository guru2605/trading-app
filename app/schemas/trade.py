from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    exchange_order_id: str
    tradingsymbol: str
    exchange: str
    transaction_type: str
    quantity: int
    price: float
    product: str
    order_type: str
    status: str
    traded_at: datetime | None
    created_at: datetime


class TradeSyncResponse(BaseModel):
    synced: int
    message: str
