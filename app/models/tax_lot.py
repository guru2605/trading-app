from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaxLot(Base):
    __tablename__ = "tax_lots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tradingsymbol: Mapped[str] = mapped_column(String(50), index=True)
    exchange: Mapped[str] = mapped_column(String(10))
    buy_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    buy_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(default=0)
    remaining_quantity: Mapped[int] = mapped_column(default=0)
    sell_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sell_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    holding_type: Mapped[str] = mapped_column(String(10), default="LTCG")  # STCG / LTCG
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
