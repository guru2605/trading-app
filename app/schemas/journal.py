from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trade_id: int | None
    tradingsymbol: str
    entry_type: str
    content: str
    tags: str
    strategy: str
    outcome: str
    emotional_state: str
    created_at: datetime
    updated_at: datetime


class JournalEntryCreateRequest(BaseModel):
    tradingsymbol: str
    entry_type: str  # pre_trade / post_trade / note
    content: str = ""
    tags: str = ""
    strategy: str = ""
    outcome: str = ""  # win / loss / breakeven
    emotional_state: str = ""  # confident / anxious / fomo / revenge / neutral
    trade_id: int | None = None


class JournalEntryUpdateRequest(BaseModel):
    tradingsymbol: str | None = None
    entry_type: str | None = None
    content: str | None = None
    tags: str | None = None
    strategy: str | None = None
    outcome: str | None = None
    emotional_state: str | None = None
    trade_id: int | None = None


class StrategyStats(BaseModel):
    strategy: str
    count: int
    wins: int
    losses: int
    win_rate: float


class TagStats(BaseModel):
    tag: str
    count: int


class JournalAnalytics(BaseModel):
    total_entries: int
    win_rate: float
    total_wins: int
    total_losses: int
    total_breakeven: int
    by_strategy: list[StrategyStats]
    by_tag: list[TagStats]
