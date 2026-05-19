from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BehaviorFlag(Base):
    __tablename__ = "behavior_flags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    flag_type: Mapped[str] = mapped_column(String(50), index=True)  # overtrading, revenge_trade, etc.
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info / warning / critical
    description: Mapped[str] = mapped_column(Text, default="")
    trade_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
