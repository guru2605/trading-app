from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.sector_map import SectorMap
from app.services.risk import RiskSnapshotService


async def test_create_snapshot_from_holdings(db_session: AsyncSession) -> None:
    db_session.add(
        Holding(
            tradingsymbol="INFY",
            exchange="NSE",
            quantity=10,
            average_price=1500.0,
            last_price=1600.0,
            day_change=10.0,
        )
    )
    db_session.add(
        Holding(
            tradingsymbol="TCS",
            exchange="NSE",
            quantity=5,
            average_price=3500.0,
            last_price=3400.0,
            day_change=-20.0,
        )
    )
    db_session.add(SectorMap(tradingsymbol="INFY", sector="IT"))
    db_session.add(SectorMap(tradingsymbol="TCS", sector="IT"))
    await db_session.commit()

    service = RiskSnapshotService(db_session)
    snapshot = await service.create_snapshot()

    assert snapshot.total_invested == 32500.0  # 15000 + 17500
    assert snapshot.total_current == 33000.0  # 16000 + 17000
    assert snapshot.total_pnl == 500.0
    assert snapshot.day_pnl == 0.0  # (10*10) + (5*-20) = 0
    assert snapshot.sector_concentration == {"IT": 100.0}
    assert len(snapshot.details["holdings"]) == 2


async def test_create_snapshot_empty_holdings(db_session: AsyncSession) -> None:
    service = RiskSnapshotService(db_session)
    snapshot = await service.create_snapshot()

    assert snapshot.total_invested == 0.0
    assert snapshot.total_current == 0.0
    assert snapshot.total_pnl == 0.0
    assert snapshot.max_single_stock_pct == 0.0


async def test_list_snapshots(db_session: AsyncSession) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    await db_session.commit()

    service = RiskSnapshotService(db_session)
    await service.create_snapshot()
    await service.create_snapshot()

    snapshots = await service.list_snapshots()
    assert len(snapshots) == 2


async def test_get_latest_snapshot(db_session: AsyncSession) -> None:
    service = RiskSnapshotService(db_session)

    # No snapshots yet
    latest = await service.get_latest()
    assert latest is None

    # Create one
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    await db_session.commit()

    await service.create_snapshot()
    latest = await service.get_latest()
    assert latest is not None
    assert latest.total_current == 16000.0


async def test_list_snapshots_respects_limit(db_session: AsyncSession) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    await db_session.commit()

    service = RiskSnapshotService(db_session)
    for _ in range(5):
        await service.create_snapshot()

    snapshots = await service.list_snapshots(limit=3)
    assert len(snapshots) == 3
