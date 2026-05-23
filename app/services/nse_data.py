"""NSE data service — fetches delivery volume % and FII/DII activity from NSE."""

import csv
import io
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NSE_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}

BHAVCOPY_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
FII_DII_URL = "https://www.nseindia.com/api/fiidiiActivity"


class NseDataService:
    """Fetches delivery volume data and FII/DII flows from NSE."""

    def __init__(self) -> None:
        self._delivery_cache: dict[str, dict[str, float]] = {}
        self._fii_dii_cache: dict[str, dict[str, Any]] | None = None
        self._cache_date: str = ""

    async def fetch_delivery_data(self, tradingsymbol: str) -> dict[str, Any]:
        """Fetch delivery volume percentage for a stock from NSE bhavcopy.

        Returns dict with delivery_pct and delivery_qty, or available=False.
        """
        today = datetime.now(UTC).strftime("%d%m%Y")

        # Use cache if available for today
        if self._cache_date == today and tradingsymbol in self._delivery_cache:
            cached = self._delivery_cache[tradingsymbol]
            return {"available": True, **cached}

        # Try last 3 trading days (weekends/holidays may not have data)
        for days_ago in range(0, 4):
            date = datetime.now(UTC) - timedelta(days=days_ago)
            date_str = date.strftime("%d%m%Y")
            url = BHAVCOPY_URL.format(date=date_str)

            try:
                data = await self._download_bhavcopy(url)
                if data:
                    self._delivery_cache = data
                    self._cache_date = today
                    if tradingsymbol in data:
                        return {"available": True, **data[tradingsymbol]}
                    return {"available": False}
            except Exception:
                continue

        return {"available": False}

    async def _download_bhavcopy(self, url: str) -> dict[str, dict[str, float]]:
        """Download and parse NSE bhavcopy CSV. Returns {symbol: {delivery_pct, delivery_qty}}."""
        result: dict[str, dict[str, float]] = {}
        try:
            async with httpx.AsyncClient(headers=NSE_HEADERS, timeout=15.0, follow_redirects=True) as client:
                # First hit NSE homepage to get cookies
                await client.get("https://www.nseindia.com/")
                resp = await client.get(url)
                if resp.status_code != 200:
                    return {}

                reader = csv.DictReader(io.StringIO(resp.text))
                for row in reader:
                    symbol = row.get("SYMBOL", "").strip()
                    if not symbol:
                        continue
                    try:
                        traded_qty = float(row.get("TTL_TRD_QNTY", "0") or "0")
                        delivery_qty = float(row.get("DELIV_QTY", "0") or "0")
                        delivery_pct = (delivery_qty / traded_qty * 100) if traded_qty > 0 else 0.0
                        result[symbol] = {
                            "delivery_pct": round(delivery_pct, 2),
                            "delivery_qty": delivery_qty,
                        }
                    except (ValueError, ZeroDivisionError):
                        continue
        except Exception:
            logger.debug("Failed to download bhavcopy from %s", url)
        return result

    async def fetch_fii_dii_activity(self) -> dict[str, Any]:
        """Fetch today's FII/DII net buy/sell activity from NSE.

        Returns dict with fii_net (Cr), dii_net (Cr), or available=False.
        """
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._fii_dii_cache is not None and self._cache_date == today:
            return self._fii_dii_cache

        try:
            async with httpx.AsyncClient(headers=NSE_HEADERS, timeout=15.0, follow_redirects=True) as client:
                # Get cookies first
                await client.get("https://www.nseindia.com/")
                resp = await client.get(FII_DII_URL)
                if resp.status_code != 200:
                    return {"available": False}

                data = resp.json()
                fii_net = 0.0
                dii_net = 0.0

                for entry in data:
                    category = entry.get("category", "")
                    net_value = float(entry.get("netValue", "0") or "0")
                    if "FII" in category or "FPI" in category:
                        fii_net += net_value
                    elif "DII" in category:
                        dii_net += net_value

                result: dict[str, Any] = {
                    "available": True,
                    "fii_net": round(fii_net, 2),
                    "dii_net": round(dii_net, 2),
                    "fii_buying": fii_net > 500,
                    "fii_selling": fii_net < -500,
                }
                self._fii_dii_cache = result
                self._cache_date = today
                return result

        except Exception:
            logger.debug("Failed to fetch FII/DII activity")
        return {"available": False}
