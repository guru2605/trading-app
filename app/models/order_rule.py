from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderRule(Base):
    __tablename__ = "order_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    tradingsymbol: Mapped[str] = mapped_column(String(50), index=True)
    exchange: Mapped[str] = mapped_column(String(10))
    transaction_type: Mapped[str] = mapped_column(String(10))  # BUY / SELL
    quantity: Mapped[int] = mapped_column(default=0)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    trigger_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    product: Mapped[str] = mapped_column(String(10), default="CNC")
    order_type: Mapped[str] = mapped_column(String(10), default="MARKET")
    condition: Mapped[str] = mapped_column(Text, default="")  # JSON condition expression
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
