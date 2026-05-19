from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    entity_type: str
    entity_id: str | None
    payload: dict[str, Any]
    source: str
    created_at: datetime


class AuditEventListResponse(BaseModel):
    events: list[AuditEventResponse]
    total: int
    limit: int
    offset: int
