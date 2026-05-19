from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(50), index=True)
    exchange_order_id: Mapped[str] = mapped_column(String(50), default="")
    tradingsymbol: Mapped[str] = mapped_column(String(50), index=True)
    exchange: Mapped[str] = mapped_column(String(10))
    transaction_type: Mapped[str] = mapped_column(String(10))  # BUY / SELL
    quantity: Mapped[int] = mapped_column(default=0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    product: Mapped[str] = mapped_column(String(10))  # CNC / MIS / NRML
    order_type: Mapped[str] = mapped_column(String(10))  # MARKET / LIMIT / SL / SL-M
    status: Mapped[str] = mapped_column(String(20), default="COMPLETE")
    traded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
