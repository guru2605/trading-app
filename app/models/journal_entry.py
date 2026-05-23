from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    tradingsymbol: Mapped[str] = mapped_column(String(50), index=True)
    entry_type: Mapped[str] = mapped_column(String(20))  # pre_trade / post_trade / note
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(500), default="")  # comma-separated
    strategy: Mapped[str] = mapped_column(String(50), default="")  # breakout, mean_reversion, scalp
    outcome: Mapped[str] = mapped_column(String(20), default="")  # win, loss, breakeven
    emotional_state: Mapped[str] = mapped_column(String(30), default="")  # confident, anxious, fomo, revenge, neutral
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
