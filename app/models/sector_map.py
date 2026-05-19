from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SectorMap(Base):
    __tablename__ = "sector_maps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tradingsymbol: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    sector: Mapped[str] = mapped_column(String(100), index=True)
    industry: Mapped[str] = mapped_column(String(100), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
