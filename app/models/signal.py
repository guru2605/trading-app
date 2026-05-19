from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tradingsymbol: Mapped[str] = mapped_column(String(50), index=True)
    exchange: Mapped[str] = mapped_column(String(10), default="NSE")
    signal_type: Mapped[str] = mapped_column(String(10), index=True)  # BUY / SELL
    timeframe: Mapped[str] = mapped_column(String(20), default="15minute")
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    target_price: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)  # 0-100
    indicators: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active / executed / expired
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
