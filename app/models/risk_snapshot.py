from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    total_invested: Mapped[float] = mapped_column(Float, default=0.0)
    total_current: Mapped[float] = mapped_column(Float, default=0.0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    day_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    max_single_stock_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sector_concentration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
