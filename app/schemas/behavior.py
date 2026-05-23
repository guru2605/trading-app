from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BehaviorFlagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    flag_type: str
    severity: str
    description: str
    trade_id: int | None
    is_acknowledged: bool
    created_at: datetime


class BehaviorDetectionResponse(BaseModel):
    flags: list[BehaviorFlagResponse]
    summary: str


class BehaviorAcknowledgeRequest(BaseModel):
    is_acknowledged: bool


class BehaviorSummary(BaseModel):
    total: int
    by_severity: dict[str, int]
    unacknowledged: int
    recent_flags: list[BehaviorFlagResponse]
