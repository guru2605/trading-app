from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import AuditService


async def test_list_audit_events_empty(client: AsyncClient) -> None:
    response = await client.get("/api/audit/events")
    assert response.status_code == 200
    data = response.json()
    assert data["events"] == []
    assert data["total"] == 0


async def test_list_audit_events_with_data(client: AsyncClient, db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    await service.log(event_type="test.event", entity_type="test", payload={"foo": "bar"})

    response = await client.get("/api/audit/events")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["events"][0]["event_type"] == "test.event"
    assert data["events"][0]["payload"] == {"foo": "bar"}


async def test_list_audit_events_with_filters(client: AsyncClient, db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    await service.log(event_type="auth.login", entity_type="session", source="kite")
    await service.log(event_type="trade.placed", entity_type="trade", source="system")

    response = await client.get("/api/audit/events", params={"event_type": "auth.login"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["events"][0]["event_type"] == "auth.login"


async def test_get_audit_event(client: AsyncClient, db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    event = await service.log(event_type="test.get", entity_type="test")

    response = await client.get(f"/api/audit/events/{event.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == event.id
    assert data["event_type"] == "test.get"


async def test_get_audit_event_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/audit/events/99999")
    assert response.status_code == 404
