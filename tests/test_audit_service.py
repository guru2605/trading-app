from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import AuditService


async def test_log_creates_event(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    event = await service.log(
        event_type="test.created",
        entity_type="test",
        entity_id="1",
        payload={"key": "value"},
        source="test",
    )
    assert event.id is not None
    assert event.event_type == "test.created"
    assert event.entity_type == "test"
    assert event.entity_id == "1"
    assert event.payload == {"key": "value"}
    assert event.source == "test"


async def test_list_events_empty(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    events, total = await service.list_events()
    assert events == []
    assert total == 0


async def test_list_events_with_data(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    await service.log(event_type="a.one", entity_type="a", source="s1")
    await service.log(event_type="b.two", entity_type="b", source="s2")

    events, total = await service.list_events()
    assert total == 2
    assert len(events) == 2


async def test_list_events_filter_by_event_type(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    await service.log(event_type="a.one", entity_type="a")
    await service.log(event_type="b.two", entity_type="b")

    events, total = await service.list_events(event_type="a.one")
    assert total == 1
    assert events[0].event_type == "a.one"


async def test_list_events_filter_by_entity_type(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    await service.log(event_type="x", entity_type="trade")
    await service.log(event_type="y", entity_type="alert")

    events, total = await service.list_events(entity_type="trade")
    assert total == 1
    assert events[0].entity_type == "trade"


async def test_list_events_filter_by_source(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    await service.log(event_type="x", entity_type="a", source="kite")
    await service.log(event_type="y", entity_type="b", source="system")

    events, total = await service.list_events(source="kite")
    assert total == 1
    assert events[0].source == "kite"


async def test_list_events_pagination(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    for i in range(5):
        await service.log(event_type=f"e.{i}", entity_type="t")

    events, total = await service.list_events(limit=2, offset=0)
    assert total == 5
    assert len(events) == 2

    events2, _ = await service.list_events(limit=2, offset=2)
    assert len(events2) == 2


async def test_get_event(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    created = await service.log(event_type="get.test", entity_type="x")

    fetched = await service.get_event(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.event_type == "get.test"


async def test_get_event_not_found(db_session: AsyncSession) -> None:
    service = AuditService(db_session)
    result = await service.get_event(99999)
    assert result is None
