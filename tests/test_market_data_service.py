from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.market_data import MarketDataService


def _make_yf_dataframe(n: int = 50, base: float = 100.0) -> pd.DataFrame:
    """Create a DataFrame mimicking yfinance .history() output."""
    dates = pd.date_range(start="2024-01-01", periods=n, freq="D", tz="Asia/Kolkata")
    data = {
        "Open": [base + i * 0.5 for i in range(n)],
        "High": [base + i * 0.5 + 2.0 for i in range(n)],
        "Low": [base + i * 0.5 - 1.0 for i in range(n)],
        "Close": [base + i * 0.5 + 0.5 for i in range(n)],
        "Volume": [100000 + i * 1000 for i in range(n)],
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def service() -> MarketDataService:
    return MarketDataService()


class TestMarketDataService:
    async def test_fetch_historical_nse(self, service: MarketDataService) -> None:
        df = _make_yf_dataframe(20)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("app.services.market_data.yf.Ticker", return_value=mock_ticker) as mock_yf:
            to_date = datetime.now(UTC)
            from_date = to_date - timedelta(days=365)
            result = await service.fetch_historical("RELIANCE", "NSE", from_date, to_date, "day")

            mock_yf.assert_called_once_with("RELIANCE.NS")
            mock_ticker.history.assert_called_once_with(period="1y", interval="1d")

        assert len(result) == 20
        assert all(k in result[0] for k in ("date", "open", "high", "low", "close", "volume"))
        assert isinstance(result[0]["volume"], int)
        assert isinstance(result[0]["close"], float)

    async def test_fetch_historical_bse(self, service: MarketDataService) -> None:
        df = _make_yf_dataframe(10)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("app.services.market_data.yf.Ticker", return_value=mock_ticker) as mock_yf:
            to_date = datetime.now(UTC)
            from_date = to_date - timedelta(days=365)
            result = await service.fetch_historical("RELIANCE", "BSE", from_date, to_date, "day")

            mock_yf.assert_called_once_with("RELIANCE.BO")

        assert len(result) == 10

    async def test_fetch_historical_intraday_uses_7d_period(self, service: MarketDataService) -> None:
        df = _make_yf_dataframe(30)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("app.services.market_data.yf.Ticker", return_value=mock_ticker):
            to_date = datetime.now(UTC)
            from_date = to_date - timedelta(days=7)
            await service.fetch_historical("TCS", "NSE", from_date, to_date, "15minute")

            mock_ticker.history.assert_called_once_with(period="7d", interval="15m")

    async def test_fetch_historical_empty_dataframe(self, service: MarketDataService) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("app.services.market_data.yf.Ticker", return_value=mock_ticker):
            to_date = datetime.now(UTC)
            from_date = to_date - timedelta(days=365)
            result = await service.fetch_historical("INVALID", "NSE", from_date, to_date, "day")

        assert result == []

    async def test_fetch_historical_output_format(self, service: MarketDataService) -> None:
        df = _make_yf_dataframe(5, base=500.0)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("app.services.market_data.yf.Ticker", return_value=mock_ticker):
            to_date = datetime.now(UTC)
            from_date = to_date - timedelta(days=365)
            result = await service.fetch_historical("INFY", "NSE", from_date, to_date, "day")

        # Verify Kite-compatible format
        for candle in result:
            assert isinstance(candle["date"], datetime)
            assert isinstance(candle["open"], float)
            assert isinstance(candle["high"], float)
            assert isinstance(candle["low"], float)
            assert isinstance(candle["close"], float)
            assert isinstance(candle["volume"], int)
            assert candle["high"] >= candle["low"]
