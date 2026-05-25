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

    _intermarket_cache: dict[str, dict[str, Any]] = {}

    async def fetch_intermarket_data(self) -> dict[str, Any]:
        """Fetch intermarket data (USD/INR, Crude, S&P 500, US 10Y) and compute risk-on score.

        Cached per date since these change daily. Score 0-4: higher = more risk-on.
        """
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today in self._intermarket_cache:
            return self._intermarket_cache[today]

        symbols = {"sp500": "^GSPC", "usdinr": "USDINR=X", "crude": "CL=F", "us10y": "^TNX"}
        returns: dict[str, float | None] = {}

        try:
            for key, ticker in symbols.items():
                try:
                    df = await asyncio.to_thread(
                        lambda t=ticker: yf.Ticker(t).history(period="10d", interval="1d")  # type: ignore[misc]
                    )
                    if df is not None and len(df) >= 6:
                        close_now = float(df["Close"].iloc[-1])
                        close_5d = float(df["Close"].iloc[-6])
                        if close_5d > 0:
                            returns[key] = (close_now - close_5d) / close_5d * 100
                        else:
                            returns[key] = None
                    else:
                        returns[key] = None
                except Exception:
                    returns[key] = None

            risk_on_score = 0
            sp_ret = returns.get("sp500")
            if sp_ret is not None and sp_ret > 0:
                risk_on_score += 1

            usdinr_ret = returns.get("usdinr")
            if usdinr_ret is not None and abs(usdinr_ret) < 1.0:
                risk_on_score += 1

            crude_ret = returns.get("crude")
            if crude_ret is not None and crude_ret <= 0:
                risk_on_score += 1

            us10y_ret = returns.get("us10y")
            if us10y_ret is not None and us10y_ret <= 0:
                risk_on_score += 1

            result: dict[str, Any] = {
                "available": True,
                "risk_on_score": risk_on_score,
                "risk_on": risk_on_score >= 3,
                "risk_off": risk_on_score <= 1,
                "sp500_return_5d": returns.get("sp500"),
                "usdinr_return_5d": returns.get("usdinr"),
                "crude_return_5d": returns.get("crude"),
                "us10y_return_5d": returns.get("us10y"),
            }
            self._intermarket_cache[today] = result
            return result

        except Exception:
            logger.warning("Failed to fetch intermarket data")
        return {"available": False}

    _sector_rotation_cache: dict[str, dict[str, Any]] = {}

    async def fetch_sector_rotation(self) -> dict[str, dict[str, Any]]:
        """Compute sector rotation analysis — RS-Ratio and RS-Momentum vs Nifty 50.

        Returns dict of {sector: {quadrant, rs_ratio, rs_momentum}}.
        Quadrants: Leading (high ratio, high momentum), Improving (low ratio, high momentum),
                  Weakening (high ratio, low momentum), Lagging (low ratio, low momentum).
        Cached per date.
        """
        from app.data.sector_mapping import SECTOR_INDICES

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today in self._sector_rotation_cache:
            return self._sector_rotation_cache[today]

        result: dict[str, dict[str, Any]] = {}

        try:
            # Fetch Nifty 50 benchmark
            nifty_df = await asyncio.to_thread(lambda: yf.Ticker("^NSEI").history(period="3mo", interval="1wk"))
            if nifty_df is None or len(nifty_df) < 10:
                return {}

            nifty_returns = nifty_df["Close"].pct_change()

            for sector, ticker in SECTOR_INDICES.items():
                try:
                    sector_df = await asyncio.to_thread(
                        lambda t=ticker: yf.Ticker(t).history(period="3mo", interval="1wk")  # type: ignore[misc]
                    )
                    if sector_df is None or len(sector_df) < 10:
                        continue

                    sector_returns = sector_df["Close"].pct_change()

                    # RS-Ratio: rolling relative strength (10-week)
                    min_len = min(len(sector_returns), len(nifty_returns))
                    if min_len < 10:
                        continue

                    sector_ret = sector_returns.iloc[-min_len:].values
                    nifty_ret = nifty_returns.iloc[-min_len:].values

                    # Cumulative relative performance over last 10 weeks
                    rs_ratio = float(sum(sector_ret[-10:]) - sum(nifty_ret[-10:])) * 100
                    # RS-Momentum: change in RS-Ratio (recent 4 weeks vs prior 4 weeks)
                    recent_rs = float(sum(sector_ret[-4:]) - sum(nifty_ret[-4:])) * 100
                    prior_rs = float(sum(sector_ret[-8:-4]) - sum(nifty_ret[-8:-4])) * 100
                    rs_momentum = recent_rs - prior_rs

                    # Classify quadrant
                    if rs_ratio > 0 and rs_momentum > 0:
                        quadrant = "Leading"
                    elif rs_ratio <= 0 and rs_momentum > 0:
                        quadrant = "Improving"
                    elif rs_ratio > 0 and rs_momentum <= 0:
                        quadrant = "Weakening"
                    else:
                        quadrant = "Lagging"

                    result[sector] = {
                        "quadrant": quadrant,
                        "rs_ratio": round(rs_ratio, 2),
                        "rs_momentum": round(rs_momentum, 2),
                    }
                except Exception:
                    continue

            self._sector_rotation_cache[today] = result

        except Exception:
            logger.warning("Failed to fetch sector rotation data")

        return result

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
