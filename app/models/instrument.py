from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_token: Mapped[int] = mapped_column(BigInteger, index=True)
    exchange_token: Mapped[int] = mapped_column(BigInteger)
    tradingsymbol: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    exchange: Mapped[str] = mapped_column(String(10), index=True)
    segment: Mapped[str] = mapped_column(String(20))
    instrument_type: Mapped[str] = mapped_column(String(20))
    lot_size: Mapped[int] = mapped_column(default=1)
    tick_size: Mapped[float] = mapped_column(Float, default=0.05)
    expiry: Mapped[str | None] = mapped_column(String(20), nullable=True)
    strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
