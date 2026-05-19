from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.instrument import Instrument
from app.services.correlation import CORRELATION_THRESHOLD, CorrelationService


@pytest.fixture
def mock_kite() -> AsyncMock:
    return AsyncMock()


async def test_correlation_single_holding(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    await db_session.commit()

    service = CorrelationService(db_session, mock_kite)
    result = await service.compute_correlation()

    assert result.symbols == ["INFY"]
    assert result.matrix == [[1.0]]
    assert len(result.high_correlations) == 0
    assert "Need at least 2 holdings" in result.warnings[0]


async def test_correlation_no_holdings(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    service = CorrelationService(db_session, mock_kite)
    result = await service.compute_correlation()

    assert result.symbols == []
    assert result.matrix == []
    assert len(result.high_correlations) == 0


async def test_correlation_computes_matrix(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    # Add two holdings and their instruments
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=5, average_price=3500.0, last_price=3400.0))
    db_session.add(
        Instrument(
            instrument_token=408065,
            exchange_token=1594,
            tradingsymbol="INFY",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
        )
    )
    db_session.add(
        Instrument(
            instrument_token=2953217,
            exchange_token=11536,
            tradingsymbol="TCS",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
        )
    )
    await db_session.commit()

    # Create correlated price data
    infy_prices = [{"close": 1500 + i * 10 + (i % 3) * 5} for i in range(20)]
    tcs_prices = [{"close": 3500 + i * 15 + (i % 3) * 8} for i in range(20)]

    async def mock_historical(token: int, from_date: object, to_date: object, interval: str) -> list[dict[str, float]]:
        if token == 408065:
            return infy_prices
        return tcs_prices

    mock_kite.historical_data = mock_historical

    service = CorrelationService(db_session, mock_kite)
    result = await service.compute_correlation()

    assert len(result.symbols) == 2
    assert len(result.matrix) == 2
    assert len(result.matrix[0]) == 2
    # Diagonal should be 1.0
    assert result.matrix[0][0] == 1.0
    assert result.matrix[1][1] == 1.0
    # Off-diagonal should be a correlation value between -1 and 1
    assert -1.0 <= result.matrix[0][1] <= 1.0


async def test_correlation_high_correlation_warning(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=5, average_price=3500.0, last_price=3400.0))
    db_session.add(
        Instrument(
            instrument_token=408065,
            exchange_token=1594,
            tradingsymbol="INFY",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
        )
    )
    db_session.add(
        Instrument(
            instrument_token=2953217,
            exchange_token=11536,
            tradingsymbol="TCS",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
        )
    )
    await db_session.commit()

    # Perfectly correlated prices
    infy_prices = [{"close": 1500 + i * 10.0} for i in range(20)]
    tcs_prices = [{"close": 3500 + i * 20.0} for i in range(20)]

    async def mock_historical(token: int, from_date: object, to_date: object, interval: str) -> list[dict[str, float]]:
        if token == 408065:
            return infy_prices
        return tcs_prices

    mock_kite.historical_data = mock_historical

    service = CorrelationService(db_session, mock_kite)
    result = await service.compute_correlation()

    # Should detect high correlation
    assert len(result.high_correlations) > 0
    assert result.high_correlations[0].correlation >= CORRELATION_THRESHOLD


async def test_correlation_concentration_warning(db_session: AsyncSession, mock_kite: AsyncMock) -> None:
    # Two holdings making up 100% of portfolio with high correlation
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=100, average_price=1500.0, last_price=1600.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=50, average_price=3500.0, last_price=3400.0))
    db_session.add(
        Instrument(
            instrument_token=408065,
            exchange_token=1594,
            tradingsymbol="INFY",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
        )
    )
    db_session.add(
        Instrument(
            instrument_token=2953217,
            exchange_token=11536,
            tradingsymbol="TCS",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
        )
    )
    await db_session.commit()

    # Perfectly correlated prices
    infy_prices = [{"close": 1500 + i * 10.0} for i in range(20)]
    tcs_prices = [{"close": 3500 + i * 20.0} for i in range(20)]

    async def mock_historical(token: int, from_date: object, to_date: object, interval: str) -> list[dict[str, float]]:
        if token == 408065:
            return infy_prices
        return tcs_prices

    mock_kite.historical_data = mock_historical

    service = CorrelationService(db_session, mock_kite)
    result = await service.compute_correlation()

    # Should have concentration warning (100% of portfolio)
    concentration_warnings = [w for w in result.warnings if "represent" in w]
    assert len(concentration_warnings) > 0
