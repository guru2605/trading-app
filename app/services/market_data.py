import asyncio
import logging
from datetime import datetime
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
