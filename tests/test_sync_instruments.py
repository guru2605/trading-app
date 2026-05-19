from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.tasks.sync_instruments import sync_instruments

MOCK_INSTRUMENTS = [
    {
        "instrument_token": 123456,
        "exchange_token": 1234,
        "tradingsymbol": "RELIANCE",
        "name": "Reliance Industries",
        "exchange": "NSE",
        "segment": "NSE",
        "instrument_type": "EQ",
        "lot_size": 1,
        "tick_size": 0.05,
        "expiry": None,
        "strike": None,
        "last_price": 2500.0,
    },
    {
        "instrument_token": 789012,
        "exchange_token": 7890,
        "tradingsymbol": "TCS",
        "name": "Tata Consultancy Services",
        "exchange": "NSE",
        "segment": "NSE",
        "instrument_type": "EQ",
        "lot_size": 1,
        "tick_size": 0.05,
        "expiry": None,
        "strike": None,
        "last_price": 3400.0,
    },
]


async def test_sync_instruments_inserts_data(db_session: AsyncSession) -> None:
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = MOCK_INSTRUMENTS

    with patch("app.tasks.sync_instruments.KiteConnect", return_value=mock_kite):
        count = await sync_instruments(db_session, access_token="test_token")

    assert count == 2

    result = await db_session.execute(select(Instrument))
    instruments = result.scalars().all()
    assert len(instruments) == 2

    symbols = {i.tradingsymbol for i in instruments}
    assert symbols == {"RELIANCE", "TCS"}


async def test_sync_instruments_replaces_existing(db_session: AsyncSession) -> None:
    # Insert an existing instrument
    db_session.add(
        Instrument(
            instrument_token=111,
            exchange_token=11,
            tradingsymbol="OLD_STOCK",
            name="Old Stock",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
        )
    )
    await db_session.commit()

    mock_kite = MagicMock()
    mock_kite.instruments.return_value = MOCK_INSTRUMENTS

    with patch("app.tasks.sync_instruments.KiteConnect", return_value=mock_kite):
        count = await sync_instruments(db_session, access_token="test_token")

    assert count == 2

    result = await db_session.execute(select(Instrument))
    instruments = result.scalars().all()
    assert len(instruments) == 2

    # OLD_STOCK should be gone
    symbols = {i.tradingsymbol for i in instruments}
    assert "OLD_STOCK" not in symbols


async def test_sync_instruments_empty_response(db_session: AsyncSession) -> None:
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = []

    with patch("app.tasks.sync_instruments.KiteConnect", return_value=mock_kite):
        count = await sync_instruments(db_session, access_token="test_token")

    assert count == 0
