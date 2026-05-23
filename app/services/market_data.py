import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

INTERVAL_MAP: dict[str, str] = {
    "5minute": "5m",
    "15minute": "15m",
    "30minute": "30m",
    "60minute": "1h",
    "day": "1d",
    "week": "1wk",
}


class MarketDataService:
    """Fetches historical OHLCV data via yfinance, returning Kite-compatible dicts."""

    async def fetch_nifty_return_5d(self) -> float | None:
        """Fetch Nifty 50 5-day return percentage. Returns None on failure."""
        try:
            df = await asyncio.to_thread(lambda: yf.Ticker("^NSEI").history(period="10d", interval="1d"))
            if df is not None and len(df) >= 6:
                close_now = float(df["Close"].iloc[-1])
                close_5d_ago = float(df["Close"].iloc[-6])
                if close_5d_ago > 0:
                    return (close_now - close_5d_ago) / close_5d_ago * 100
        except Exception:
            logger.warning("Failed to fetch Nifty 50 returns")
        return None

    async def fetch_earnings_date(self, tradingsymbol: str, exchange: str) -> datetime | None:
        """Fetch next earnings date for a stock. Returns None if unavailable."""
        yf_symbol = f"{tradingsymbol}.NS" if exchange == "NSE" else f"{tradingsymbol}.BO"
        try:
            ticker = await asyncio.to_thread(lambda: yf.Ticker(yf_symbol))
            calendar = await asyncio.to_thread(lambda: ticker.calendar)
            if calendar is not None and isinstance(calendar, dict):
                earnings_date = calendar.get("Earnings Date")
                if earnings_date and len(earnings_date) > 0:
                    ed = earnings_date[0]
                    if hasattr(ed, "to_pydatetime"):
                        return datetime.fromtimestamp(ed.to_pydatetime().timestamp(), tz=UTC)
                    if isinstance(ed, datetime):
                        return ed
        except Exception:
            logger.debug("No earnings data for %s", yf_symbol)
        return None

    async def fetch_vix(self) -> float | None:
        """Fetch latest India VIX. Returns None on failure."""
        try:
            df = await asyncio.to_thread(lambda: yf.Ticker("^INDIAVIX").history(period="5d", interval="1d"))
            if df is not None and not df.empty:
                return float(df["Close"].iloc[-1])
        except Exception:
            logger.warning("Failed to fetch India VIX")
        return None

    async def fetch_historical(
        self,
        tradingsymbol: str,
        exchange: str,
        from_date: datetime,  # noqa: ARG002
        to_date: datetime,  # noqa: ARG002
        interval: str = "day",
    ) -> list[dict[str, Any]]:
        yf_symbol = f"{tradingsymbol}.NS" if exchange == "NSE" else f"{tradingsymbol}.BO"
        yf_interval = INTERVAL_MAP.get(interval, "1d")

        period = "7d" if yf_interval in ("5m", "15m", "30m", "1h") else "1y"

        df = await asyncio.to_thread(lambda: yf.Ticker(yf_symbol).history(period=period, interval=yf_interval))

        if df is None or df.empty:
            logger.warning("No data returned from yfinance for %s", yf_symbol)
            return []

        candles: list[dict[str, Any]] = []
        for idx, row in df.iterrows():
            candles.append(
                {
                    "date": idx.to_pydatetime(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                }
            )
        return candles
