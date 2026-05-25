"""NSE data service — fetches delivery volume %, FII/DII activity, and option chains from NSE."""

import asyncio
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
OPTION_CHAIN_URL = "https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"


class NseDataService:
    """Fetches delivery volume data, FII/DII flows, and option chain from NSE."""

    def __init__(self) -> None:
        self._delivery_cache: dict[str, dict[str, float]] = {}
        self._fii_dii_cache: dict[str, dict[str, Any]] | None = None
        self._cache_date: str = ""
        self._option_cache: dict[str, dict[str, Any]] = {}
        self._option_cache_ts: dict[str, float] = {}  # symbol -> timestamp

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

    async def fetch_option_chain(self, tradingsymbol: str) -> dict[str, Any]:
        """Fetch option chain data from NSE and compute PCR, max pain, and high-OI strikes.

        Returns dict with pcr, max_pain, high_oi_ce, high_oi_pe, or available=False.
        Results are cached for 5 minutes per symbol.
        """
        import time

        now = time.time()
        if tradingsymbol in self._option_cache:
            cache_age = now - self._option_cache_ts.get(tradingsymbol, 0)
            if cache_age < 300:  # 5-minute cache
                return self._option_cache[tradingsymbol]

        try:
            url = OPTION_CHAIN_URL.format(symbol=tradingsymbol)
            async with httpx.AsyncClient(headers=NSE_HEADERS, timeout=15.0, follow_redirects=True) as client:
                await client.get("https://www.nseindia.com/")
                await asyncio.sleep(1)  # rate limiting
                resp = await client.get(url)
                if resp.status_code != 200:
                    return {"available": False}

                data = resp.json()
                records = data.get("records", {})
                chain_data = records.get("data", [])

                if not chain_data:
                    return {"available": False}

                underlying_price = records.get("underlyingValue", 0.0)

                total_ce_oi = 0.0
                total_pe_oi = 0.0
                max_ce_oi = 0.0
                max_pe_oi = 0.0
                max_ce_strike = 0.0
                max_pe_strike = 0.0
                strike_pains: dict[float, float] = {}

                for row in chain_data:
                    strike = row.get("strikePrice", 0.0)
                    ce = row.get("CE", {})
                    pe = row.get("PE", {})

                    ce_oi = float(ce.get("openInterest", 0) or 0)
                    pe_oi = float(pe.get("openInterest", 0) or 0)

                    total_ce_oi += ce_oi
                    total_pe_oi += pe_oi

                    if ce_oi > max_ce_oi:
                        max_ce_oi = ce_oi
                        max_ce_strike = strike
                    if pe_oi > max_pe_oi:
                        max_pe_oi = pe_oi
                        max_pe_strike = strike

                    # Max pain calculation: sum of (OI * intrinsic value) for each strike
                    pain = 0.0
                    for r in chain_data:
                        s = r.get("strikePrice", 0.0)
                        c_oi = float(r.get("CE", {}).get("openInterest", 0) or 0)
                        p_oi = float(r.get("PE", {}).get("openInterest", 0) or 0)
                        pain += c_oi * max(0, s - strike) + p_oi * max(0, strike - s)
                    strike_pains[strike] = pain

                pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0.0

                max_pain = 0.0
                if strike_pains:
                    max_pain = min(strike_pains, key=strike_pains.get)  # type: ignore[arg-type]

                result: dict[str, Any] = {
                    "available": True,
                    "pcr": round(pcr, 2),
                    "max_pain": max_pain,
                    "high_oi_ce_strike": max_ce_strike,
                    "high_oi_pe_strike": max_pe_strike,
                    "total_ce_oi": total_ce_oi,
                    "total_pe_oi": total_pe_oi,
                    "underlying_price": underlying_price,
                    "bullish_pcr": pcr > 1.5,
                    "bearish_pcr": pcr < 0.7,
                    "price_above_max_pain": underlying_price > max_pain if max_pain > 0 else False,
                    "price_below_max_pain": underlying_price < max_pain if max_pain > 0 else False,
                }
                self._option_cache[tradingsymbol] = result
                self._option_cache_ts[tradingsymbol] = now
                return result

        except Exception:
            logger.debug("Failed to fetch option chain for %s", tradingsymbol)
        return {"available": False}

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
