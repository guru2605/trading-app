from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
        source: str = "system",
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
            source=source,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def list_events(
        self,
        event_type: str | None = None,
        entity_type: str | None = None,
        source: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEvent], int]:
        query = select(AuditEvent)
        count_query = select(func.count()).select_from(AuditEvent)

        if event_type:
            query = query.where(AuditEvent.event_type == event_type)
            count_query = count_query.where(AuditEvent.event_type == event_type)
        if entity_type:
            query = query.where(AuditEvent.entity_type == entity_type)
            count_query = count_query.where(AuditEvent.entity_type == entity_type)
        if source:
            query = query.where(AuditEvent.source == source)
            count_query = count_query.where(AuditEvent.source == source)

        total = (await self.db.execute(count_query)).scalar_one()
        query = query.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        events = list(result.scalars().all())
        return events, total

    async def get_event(self, event_id: int) -> AuditEvent | None:
        result = await self.db.execute(select(AuditEvent).where(AuditEvent.id == event_id))
        return result.scalar_one_or_none()
