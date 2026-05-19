from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tradingsymbol: Mapped[str] = mapped_column(String(50), index=True)
    exchange: Mapped[str] = mapped_column(String(10), default="NSE")
    notes: Mapped[str] = mapped_column(String(500), default="")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
