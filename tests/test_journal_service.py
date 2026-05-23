import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.journal import JournalService


async def test_create_entry(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    entry = await service.create_entry(
        tradingsymbol="RELIANCE",
        entry_type="post_trade",
        content="Good breakout entry",
        strategy="breakout",
        outcome="win",
    )
    assert entry.id is not None
    assert entry.tradingsymbol == "RELIANCE"
    assert entry.entry_type == "post_trade"
    assert entry.strategy == "breakout"
    assert entry.outcome == "win"


async def test_create_entry_with_trade_id(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    entry = await service.create_entry(
        tradingsymbol="INFY",
        entry_type="pre_trade",
        content="Planning entry",
        trade_id=42,
    )
    assert entry.trade_id == 42


async def test_get_entry(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    created = await service.create_entry(
        tradingsymbol="TCS",
        entry_type="note",
        content="Market observation",
    )
    fetched = await service.get_entry(created.id)
    assert fetched is not None
    assert fetched.tradingsymbol == "TCS"


async def test_get_entry_not_found(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    result = await service.get_entry(9999)
    assert result is None


async def test_list_entries(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    await service.create_entry(tradingsymbol="INFY", entry_type="post_trade", content="a")
    await service.create_entry(tradingsymbol="TCS", entry_type="pre_trade", content="b")

    entries = await service.list_entries()
    assert len(entries) == 2


async def test_list_entries_filter_symbol(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    await service.create_entry(tradingsymbol="INFY", entry_type="post_trade", content="a")
    await service.create_entry(tradingsymbol="TCS", entry_type="pre_trade", content="b")

    entries = await service.list_entries(tradingsymbol="INFY")
    assert len(entries) == 1
    assert entries[0].tradingsymbol == "INFY"


async def test_list_entries_filter_entry_type(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    await service.create_entry(tradingsymbol="INFY", entry_type="post_trade", content="a")
    await service.create_entry(tradingsymbol="TCS", entry_type="pre_trade", content="b")

    entries = await service.list_entries(entry_type="pre_trade")
    assert len(entries) == 1
    assert entries[0].entry_type == "pre_trade"


async def test_list_entries_filter_trade_id(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    await service.create_entry(tradingsymbol="INFY", entry_type="post_trade", content="a", trade_id=10)
    await service.create_entry(tradingsymbol="TCS", entry_type="pre_trade", content="b", trade_id=20)

    entries = await service.list_entries(trade_id=10)
    assert len(entries) == 1
    assert entries[0].trade_id == 10


async def test_update_entry(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    entry = await service.create_entry(
        tradingsymbol="RELIANCE",
        entry_type="post_trade",
        content="Initial",
        outcome="",
    )
    updated = await service.update_entry(entry.id, content="Updated content", outcome="win")
    assert updated is not None
    assert updated.content == "Updated content"
    assert updated.outcome == "win"


async def test_update_entry_not_found(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    result = await service.update_entry(9999, content="test")
    assert result is None


async def test_delete_entry(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    entry = await service.create_entry(tradingsymbol="INFY", entry_type="note", content="test")
    deleted = await service.delete_entry(entry.id)
    assert deleted is True

    entries = await service.list_entries()
    assert len(entries) == 0


async def test_delete_entry_not_found(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    deleted = await service.delete_entry(9999)
    assert deleted is False


async def test_analytics_empty(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    analytics = await service.get_analytics()
    assert analytics.total_entries == 0
    assert analytics.win_rate == 0.0
    assert analytics.by_strategy == []
    assert analytics.by_tag == []


async def test_analytics_win_rate(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    await service.create_entry(tradingsymbol="A", entry_type="post_trade", content="", outcome="win")
    await service.create_entry(tradingsymbol="B", entry_type="post_trade", content="", outcome="win")
    await service.create_entry(tradingsymbol="C", entry_type="post_trade", content="", outcome="loss")

    analytics = await service.get_analytics()
    assert analytics.total_entries == 3
    assert analytics.total_wins == 2
    assert analytics.total_losses == 1
    assert analytics.win_rate == pytest.approx(66.67, abs=0.1)


async def test_analytics_by_strategy(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    await service.create_entry(
        tradingsymbol="A", entry_type="post_trade", content="", strategy="breakout", outcome="win"
    )
    await service.create_entry(
        tradingsymbol="B", entry_type="post_trade", content="", strategy="breakout", outcome="loss"
    )
    await service.create_entry(tradingsymbol="C", entry_type="post_trade", content="", strategy="scalp", outcome="win")

    analytics = await service.get_analytics()
    assert len(analytics.by_strategy) == 2
    breakout = next(s for s in analytics.by_strategy if s.strategy == "breakout")
    assert breakout.count == 2
    assert breakout.wins == 1
    assert breakout.losses == 1
    assert breakout.win_rate == 50.0


async def test_analytics_by_tag(db_session: AsyncSession) -> None:
    service = JournalService(db_session)
    await service.create_entry(tradingsymbol="A", entry_type="post_trade", content="", tags="momentum,nifty50")
    await service.create_entry(tradingsymbol="B", entry_type="post_trade", content="", tags="momentum")

    analytics = await service.get_analytics()
    assert len(analytics.by_tag) == 2
    momentum = next(t for t in analytics.by_tag if t.tag == "momentum")
    assert momentum.count == 2
    nifty = next(t for t in analytics.by_tag if t.tag == "nifty50")
    assert nifty.count == 1
