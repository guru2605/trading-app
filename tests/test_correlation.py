from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.services.correlation import CORRELATION_THRESHOLD, CorrelationService


async def test_correlation_single_holding(db_session: AsyncSession) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    await db_session.commit()

    service = CorrelationService(db_session)
    result = await service.compute_correlation()

    assert result.symbols == ["INFY"]
    assert result.matrix == [[1.0]]
    assert len(result.high_correlations) == 0
    assert "Need at least 2 holdings" in result.warnings[0]


async def test_correlation_no_holdings(db_session: AsyncSession) -> None:
    service = CorrelationService(db_session)
    result = await service.compute_correlation()

    assert result.symbols == []
    assert result.matrix == []
    assert len(result.high_correlations) == 0


async def test_correlation_computes_matrix(db_session: AsyncSession) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=5, average_price=3500.0, last_price=3400.0))
    await db_session.commit()

    # Create correlated price data
    infy_prices = [{"close": 1500 + i * 10 + (i % 3) * 5} for i in range(20)]
    tcs_prices = [{"close": 3500 + i * 15 + (i % 3) * 8} for i in range(20)]

    service = CorrelationService(db_session)

    async def mock_fetch(
        symbol: str, exchange: str, from_date: object, to_date: object, interval: str
    ) -> list[dict[str, float]]:
        if symbol == "INFY":
            return infy_prices
        return tcs_prices

    with patch.object(service.market_data, "fetch_historical", side_effect=mock_fetch):
        result = await service.compute_correlation()

    assert len(result.symbols) == 2
    assert len(result.matrix) == 2
    assert len(result.matrix[0]) == 2
    # Diagonal should be 1.0
    assert result.matrix[0][0] == 1.0
    assert result.matrix[1][1] == 1.0
    # Off-diagonal should be a correlation value between -1 and 1
    assert -1.0 <= result.matrix[0][1] <= 1.0


async def test_correlation_high_correlation_warning(db_session: AsyncSession) -> None:
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=10, average_price=1500.0, last_price=1600.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=5, average_price=3500.0, last_price=3400.0))
    await db_session.commit()

    # Perfectly correlated prices
    infy_prices = [{"close": 1500 + i * 10.0} for i in range(20)]
    tcs_prices = [{"close": 3500 + i * 20.0} for i in range(20)]

    service = CorrelationService(db_session)

    async def mock_fetch(
        symbol: str, exchange: str, from_date: object, to_date: object, interval: str
    ) -> list[dict[str, float]]:
        if symbol == "INFY":
            return infy_prices
        return tcs_prices

    with patch.object(service.market_data, "fetch_historical", side_effect=mock_fetch):
        result = await service.compute_correlation()

    # Should detect high correlation
    assert len(result.high_correlations) > 0
    assert result.high_correlations[0].correlation >= CORRELATION_THRESHOLD


async def test_correlation_concentration_warning(db_session: AsyncSession) -> None:
    # Two holdings making up 100% of portfolio with high correlation
    db_session.add(Holding(tradingsymbol="INFY", exchange="NSE", quantity=100, average_price=1500.0, last_price=1600.0))
    db_session.add(Holding(tradingsymbol="TCS", exchange="NSE", quantity=50, average_price=3500.0, last_price=3400.0))
    await db_session.commit()

    # Perfectly correlated prices
    infy_prices = [{"close": 1500 + i * 10.0} for i in range(20)]
    tcs_prices = [{"close": 3500 + i * 20.0} for i in range(20)]

    service = CorrelationService(db_session)

    async def mock_fetch(
        symbol: str, exchange: str, from_date: object, to_date: object, interval: str
    ) -> list[dict[str, float]]:
        if symbol == "INFY":
            return infy_prices
        return tcs_prices

    with patch.object(service.market_data, "fetch_historical", side_effect=mock_fetch):
        result = await service.compute_correlation()

    # Should have concentration warning (100% of portfolio)
    concentration_warnings = [w for w in result.warnings if "represent" in w]
    assert len(concentration_warnings) > 0
