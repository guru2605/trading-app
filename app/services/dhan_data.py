"""DhanHQ market data adapter — alternative data source with same interface as MarketDataService.

Activated via MARKET_DATA_PROVIDER=dhan env var. Provides:
- 3-year historical data (vs 1-year from yfinance)
- Option chains with real-time OI
- WebSocket streaming

Requires `dhanhq` package: poetry add dhanhq
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_DHAN_AVAILABLE = False
try:
    from dhanhq import dhanhq as dhan_client

    _DHAN_AVAILABLE = True
except ImportError:
    pass

# Interval mapping: our interval names → DhanHQ interval constants
INTERVAL_MAP: dict[str, str] = {
    "5minute": "5",
    "15minute": "15",
    "30minute": "30",
    "60minute": "60",
    "day": "D",
    "week": "W",
}

# Exchange segment mapping
EXCHANGE_MAP: dict[str, str] = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
}


class DhanDataService:
    """Market data service using DhanHQ API. Same interface as MarketDataService."""

    def __init__(self, client_id: str = "", access_token: str = "") -> None:
        self._client: Any = None
        self._client_id = client_id
        self._access_token = access_token
        if _DHAN_AVAILABLE and client_id and access_token:
            try:
                self._client = dhan_client(client_id, access_token)
                logger.info("DhanHQ client initialized")
            except Exception:
                logger.warning("Failed to initialize DhanHQ client")

    @property
    def available(self) -> bool:
        return self._client is not None

    async def fetch_historical(
        self,
        tradingsymbol: str,
        exchange: str,
        from_date: datetime,
        to_date: datetime,
        interval: str = "day",
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLCV data via DhanHQ.

        Returns Kite-compatible candle dicts.
        """
        if not self.available:
            return []

        dhan_interval = INTERVAL_MAP.get(interval, "D")
        exchange_segment = EXCHANGE_MAP.get(exchange, "NSE_EQ")

        try:
            security_id = await self._resolve_security_id(tradingsymbol, exchange_segment)
            if not security_id:
                return []

            data = await asyncio.to_thread(
                lambda: self._client.historical_data(
                    security_id=security_id,
                    exchange_segment=exchange_segment,
                    instrument_type="EQUITY",
                    expiry_code=0,
                    from_date=from_date.strftime("%Y-%m-%d"),
                    to_date=to_date.strftime("%Y-%m-%d"),
                    interval=dhan_interval,
                )
            )

            if not data or data.get("status") != "success":
                return []

            candles: list[dict[str, Any]] = []
            for row in data.get("data", []):
                candles.append(
                    {
                        "date": datetime.strptime(row["start_Time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row["volume"]),
                    }
                )
            return candles

        except Exception:
            logger.warning("DhanHQ fetch_historical failed for %s", tradingsymbol)
            return []

    async def fetch_vix(self) -> float | None:
        """Fetch India VIX. DhanHQ doesn't provide this directly — fallback to None."""
        return None

    async def fetch_nifty_return_5d(self) -> float | None:
        """Fetch Nifty 50 5-day return. Uses DhanHQ historical data for Nifty index."""
        if not self.available:
            return None

        try:
            to_date = datetime.now(UTC)
            from_date = to_date - timedelta(days=10)
            nifty_id = "13"  # Nifty 50 security ID on DhanHQ

            data = await asyncio.to_thread(
                lambda: self._client.historical_data(
                    security_id=nifty_id,
                    exchange_segment="NSE_EQ",
                    instrument_type="INDEX",
                    expiry_code=0,
                    from_date=from_date.strftime("%Y-%m-%d"),
                    to_date=to_date.strftime("%Y-%m-%d"),
                    interval="D",
                )
            )

            if data and data.get("status") == "success":
                rows = data.get("data", [])
                if len(rows) >= 6:
                    close_now = float(rows[-1]["close"])
                    close_5d = float(rows[-6]["close"])
                    if close_5d > 0:
                        return (close_now - close_5d) / close_5d * 100
        except Exception:
            logger.warning("DhanHQ fetch_nifty_return_5d failed")
        return None

    async def fetch_earnings_date(self, tradingsymbol: str, exchange: str) -> datetime | None:  # noqa: ARG002
        """DhanHQ doesn't provide earnings dates — returns None."""
        return None

    async def fetch_intermarket_data(self) -> dict[str, Any]:
        """DhanHQ doesn't provide international data — returns unavailable."""
        return {"available": False}

    async def fetch_sector_rotation(self) -> dict[str, dict[str, Any]]:
        """DhanHQ doesn't provide sector indices directly — returns empty."""
        return {}

    _security_id_cache: dict[str, str] = {}

    async def _resolve_security_id(self, tradingsymbol: str, exchange_segment: str) -> str | None:
        """Resolve trading symbol to DhanHQ security ID. Cached."""
        cache_key = f"{exchange_segment}:{tradingsymbol}"
        if cache_key in self._security_id_cache:
            return self._security_id_cache[cache_key]

        try:
            # DhanHQ uses security master CSV for symbol resolution
            # This is a simplified version — production would load the full master
            result = await asyncio.to_thread(
                lambda: self._client.search_scrip(tradingsymbol)
            )
            if result and isinstance(result, list) and len(result) > 0:
                sec_id = str(result[0].get("SEM_SMST_SECURITY_ID", ""))
                if sec_id:
                    self._security_id_cache[cache_key] = sec_id
                    return sec_id
        except Exception:
            logger.debug("Failed to resolve security ID for %s", tradingsymbol)
        return None
