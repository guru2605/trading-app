from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade
from app.services.behavior import BehaviorDetectionService


async def _insert_trade(
    db: AsyncSession,
    tradingsymbol: str = "RELIANCE",
    transaction_type: str = "BUY",
    quantity: int = 10,
    price: float = 100.0,
    traded_at: datetime | None = None,
) -> Trade:
    trade = Trade(
        order_id=f"ORD-{id(traded_at)}",
        tradingsymbol=tradingsymbol,
        exchange="NSE",
        transaction_type=transaction_type,
        quantity=quantity,
        price=price,
        product="CNC",
        order_type="MARKET",
        traded_at=traded_at or datetime.now(UTC),
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return trade


async def test_detect_overtrading(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for i in range(16):
        await _insert_trade(db_session, traded_at=now - timedelta(minutes=i))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_overtrading()
    assert len(flags) == 1
    assert flags[0].flag_type == "overtrading"
    assert flags[0].severity == "warning"


async def test_detect_overtrading_no_flag(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for i in range(10):
        await _insert_trade(db_session, traded_at=now - timedelta(minutes=i))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_overtrading()
    assert len(flags) == 0


async def test_detect_revenge_trading(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # Buy at 100
    await _insert_trade(db_session, transaction_type="BUY", price=100.0, traded_at=now - timedelta(minutes=10))
    # Sell at 90 (loss)
    await _insert_trade(db_session, transaction_type="SELL", price=90.0, traded_at=now - timedelta(minutes=5))
    # Re-buy within 3 minutes (revenge)
    await _insert_trade(db_session, transaction_type="BUY", price=91.0, traded_at=now - timedelta(minutes=3))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_revenge_trading()
    assert len(flags) == 1
    assert flags[0].flag_type == "revenge_trade"
    assert flags[0].severity == "critical"


async def test_detect_revenge_trading_no_flag(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # Buy at 100
    await _insert_trade(db_session, transaction_type="BUY", price=100.0, traded_at=now - timedelta(minutes=30))
    # Sell at 90 (loss)
    await _insert_trade(db_session, transaction_type="SELL", price=90.0, traded_at=now - timedelta(minutes=20))
    # Re-buy after 10 minutes (not revenge, > 5 min)
    await _insert_trade(db_session, transaction_type="BUY", price=91.0, traded_at=now - timedelta(minutes=10))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_revenge_trading()
    assert len(flags) == 0


async def test_detect_position_spike(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # 20 small trades
    for i in range(20):
        await _insert_trade(db_session, quantity=10, price=100.0, traded_at=now - timedelta(hours=20 - i))
    # 1 big trade (3x average)
    await _insert_trade(db_session, quantity=30, price=100.0, traded_at=now)

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_position_spike()
    assert len(flags) == 1
    assert flags[0].flag_type == "position_spike"
    assert flags[0].severity == "warning"


async def test_detect_position_spike_no_flag(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for i in range(5):
        await _insert_trade(db_session, quantity=10, price=100.0, traded_at=now - timedelta(hours=5 - i))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_position_spike()
    assert len(flags) == 0


async def test_detect_loss_streak_info(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # 3 consecutive losing trades: buy high, sell low
    for i in range(3):
        await _insert_trade(db_session, transaction_type="BUY", price=100.0, traded_at=now - timedelta(hours=6 - i * 2))
        await _insert_trade(db_session, transaction_type="SELL", price=90.0, traded_at=now - timedelta(hours=5 - i * 2))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_loss_streak()
    assert len(flags) == 1
    assert flags[0].flag_type == "loss_streak"
    assert flags[0].severity == "info"


async def test_detect_loss_streak_warning(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # 5 consecutive losing trades
    for i in range(5):
        await _insert_trade(
            db_session, transaction_type="BUY", price=100.0, traded_at=now - timedelta(hours=10 - i * 2)
        )
        await _insert_trade(db_session, transaction_type="SELL", price=90.0, traded_at=now - timedelta(hours=9 - i * 2))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_loss_streak()
    assert len(flags) == 1
    assert flags[0].severity == "warning"


async def test_detect_averaging_down(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # 3 successive BUYs at decreasing prices
    await _insert_trade(db_session, transaction_type="BUY", price=100.0, traded_at=now - timedelta(hours=3))
    await _insert_trade(db_session, transaction_type="BUY", price=95.0, traded_at=now - timedelta(hours=2))
    await _insert_trade(db_session, transaction_type="BUY", price=90.0, traded_at=now - timedelta(hours=1))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_averaging_down()
    assert len(flags) == 1
    assert flags[0].flag_type == "averaging_down"
    assert flags[0].severity == "warning"


async def test_detect_averaging_down_no_flag(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # Prices going up — not averaging down
    await _insert_trade(db_session, transaction_type="BUY", price=90.0, traded_at=now - timedelta(hours=3))
    await _insert_trade(db_session, transaction_type="BUY", price=95.0, traded_at=now - timedelta(hours=2))
    await _insert_trade(db_session, transaction_type="BUY", price=100.0, traded_at=now - timedelta(hours=1))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_averaging_down()
    assert len(flags) == 0


async def test_acknowledge_flag(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for i in range(16):
        await _insert_trade(db_session, traded_at=now - timedelta(minutes=i))

    service = BehaviorDetectionService(db_session)
    flags = await service._detect_overtrading()
    assert len(flags) == 1

    acked = await service.acknowledge_flag(flags[0].id, True)
    assert acked is not None
    assert acked.is_acknowledged is True


async def test_acknowledge_flag_not_found(db_session: AsyncSession) -> None:
    service = BehaviorDetectionService(db_session)
    result = await service.acknowledge_flag(9999, True)
    assert result is None


async def test_get_summary(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for i in range(16):
        await _insert_trade(db_session, traded_at=now - timedelta(minutes=i))

    service = BehaviorDetectionService(db_session)
    await service._detect_overtrading()

    summary = await service.get_summary()
    assert summary.total == 1
    assert summary.unacknowledged == 1
    assert "warning" in summary.by_severity
    assert len(summary.recent_flags) == 1
