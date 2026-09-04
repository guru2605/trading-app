"""NIFTY index minute candles from Kite Connect, cached to SQLite — READ ONLY.

PAPER TRADING ONLY. This module reads two Kite Connect endpoints — the NSE instrument dump
(to resolve the index instrument token) and ``/instruments/historical/...`` — and writes rows
to a local SQLite cache. It places, modifies and cancels nothing; the ``kiteconnect`` SDK is
deliberately not imported (see app.options.broker's docstring for why).

This is the data source for the Phase 2 index-level signal test (plan doc § Phase 2 revised).
Index minute candles are included in the Rs 500/mo Connect subscription at no extra cost,
which is the whole reason the withdrawn expired-options backtest could be replaced at all.

Kite's constraints, from https://kite.trade/docs/connect/v3/historical/ :

* ``minute`` candles are capped at **60 days per request**, so a multi-year pull is chunked.
* Historical is rate limited to 3 requests/second; this fetches well under that.
* A candle timestamp is the **start** of the minute, in IST, e.g. the 09:15 candle covers
  09:15:00–09:15:59. Index candles carry no meaningful volume, so volume is not stored.

The cache is append-only and idempotent: every chunk fetched is recorded in ``fetch_chunks``,
so a re-run pulls only what is missing. Delete the DB to force a full refetch.

Run::

    python -m app.options.histdata --from 2019-01-01 --to 2026-09-04
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from app.options.broker import (
    KITE_API_BASE,
    KITE_VERSION_HEADER,
    REQUEST_TIMEOUT_SECONDS,
    StoredToken,
    api_key,
    require_fresh_token,
)
from app.options.calendar import IST

# ── Kite parameters ──────────────────────────────────────────────────────────────────────

INSTRUMENTS_NSE_URL = KITE_API_BASE + "/instruments/NSE"
HISTORICAL_URL_TEMPLATE = KITE_API_BASE + "/instruments/historical/{token}/{interval}"

#: Kite caps ``minute`` history at 60 days per request. Source: Kite Connect v3 historical docs.
MAX_DAYS_PER_REQUEST = 60

#: Historical endpoints allow 3 req/s. One request per chunk with this pause stays under it
#: with a wide margin — a 7-year pull is ~43 requests, so throughput is irrelevant here.
REQUEST_PAUSE_SECONDS = 0.5

#: Kite's tradingsymbol for the index we test. The NSE dump's index rows carry segment
#: "INDICES"; the token is resolved from the dump rather than hard-coded (it is 256265 today,
#: but a magic number that silently goes stale is exactly the failure mode this project keeps
#: finding in its own spec).
NIFTY_TRADINGSYMBOL = "NIFTY 50"
KITE_SEGMENT_INDICES = "INDICES"

CANDLE_INTERVAL = "minute"

DEFAULT_CANDLE_DB = Path("data/options/nifty_minute.db")

#: Kite serves index minute history from 2015; this is the default pull start. Earlier data
#: exists but the NSE session structure differs enough (pre-2015 the close was 15:30 with a
#: different pre-open regime) that stretching further buys noise, not power.
DEFAULT_HISTORY_START = date(2019, 1, 1)


# ── SQLite cache ─────────────────────────────────────────────────────────────────────────

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS candles (
    ts    TEXT PRIMARY KEY,  -- bar START, IST ISO-8601 (Kite's own format)
    open  REAL NOT NULL,
    high  REAL NOT NULL,
    low   REAL NOT NULL,
    close REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_candles_day ON candles (substr(ts, 1, 10));

-- Which date ranges have been pulled, so a re-run fetches only the gaps. A holiday-only
-- chunk legitimately returns zero candles; without this table it would be refetched forever.
CREATE TABLE IF NOT EXISTS fetch_chunks (
    from_date  TEXT NOT NULL,
    to_date    TEXT NOT NULL,
    candles    INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (from_date, to_date)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_DDL)


@dataclass(frozen=True)
class Bar:
    """One index minute candle. ``ts`` is the bar's start, tz-aware IST."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float


def chunk_ranges(start: date, end: date, size_days: int = MAX_DAYS_PER_REQUEST) -> list[tuple[date, date]]:
    """Split [start, end] into inclusive ranges no longer than Kite's per-request cap."""
    if size_days <= 0:
        raise ValueError("chunk size must be positive")
    if end < start:
        return []
    chunks = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=size_days - 1), end)
        chunks.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return chunks


def missing_chunks(conn: sqlite3.Connection, start: date, end: date) -> list[tuple[date, date]]:
    """Chunks of [start, end] not already recorded in ``fetch_chunks``."""
    done = {(row[0], row[1]) for row in conn.execute("SELECT from_date, to_date FROM fetch_chunks")}
    return [(a, b) for a, b in chunk_ranges(start, end) if (a.isoformat(), b.isoformat()) not in done]


def parse_timestamp(raw: str) -> datetime:
    """Parse a Kite candle timestamp, e.g. ``2026-06-03T09:15:00+0530``.

    Kite writes the UTC offset without a colon. ``datetime.fromisoformat`` only accepts that
    form from Python 3.11 on, and this repo's Poetry env is 3.10 — so the colon is inserted
    rather than left to the interpreter version.
    """
    if len(raw) >= 5 and raw[-5] in "+-" and raw[-3] != ":":
        raw = raw[:-2] + ":" + raw[-2:]
    return datetime.fromisoformat(raw).astimezone(IST)


def parse_candles(payload: dict) -> list[Bar]:  # type: ignore[type-arg]
    """Kite's ``[[ts, o, h, l, c, v], ...]`` into Bars. Volume is dropped: indices have none."""
    bars = []
    for row in payload.get("data", {}).get("candles", []):
        ts, open_, high, low, close = row[0], row[1], row[2], row[3], row[4]
        bars.append(
            Bar(
                ts=parse_timestamp(ts),
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
            )
        )
    return bars


def store_candles(conn: sqlite3.Connection, bars: Sequence[Bar]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO candles (ts, open, high, low, close) VALUES (?, ?, ?, ?, ?)",
        [(bar.ts.isoformat(), bar.open, bar.high, bar.low, bar.close) for bar in bars],
    )


def load_days(conn: sqlite3.Connection, start: date | None = None, end: date | None = None) -> Iterator[list[Bar]]:
    """Every cached session's bars, oldest first, each already sorted by time.

    A "session" is simply a calendar date that has candles — the exchange's own answer to
    "was this a trading day", which needs no holiday table and covers years the hand-written
    :mod:`app.options.calendar` list does not.
    """
    sql = "SELECT ts, open, high, low, close FROM candles"
    params: list[str] = []
    clauses = []
    if start is not None:
        clauses.append("substr(ts, 1, 10) >= ?")
        params.append(start.isoformat())
    if end is not None:
        clauses.append("substr(ts, 1, 10) <= ?")
        params.append(end.isoformat())
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY ts"

    current_day: date | None = None
    bars: list[Bar] = []
    for ts, open_, high, low, close in conn.execute(sql, params):
        bar = Bar(datetime.fromisoformat(ts), float(open_), float(high), float(low), float(close))
        if current_day is not None and bar.ts.date() != current_day:
            yield bars
            bars = []
        current_day = bar.ts.date()
        bars.append(bar)
    if bars:
        yield bars


# ── Kite REST access (read-only) ─────────────────────────────────────────────────────────


def _auth_headers(token: StoredToken) -> dict[str, str]:
    return {**KITE_VERSION_HEADER, "Authorization": f"token {api_key()}:{token.access_token}"}


def find_index_token(instruments: Sequence[dict[str, str]], tradingsymbol: str = NIFTY_TRADINGSYMBOL) -> int:
    """Resolve an index's instrument_token from Kite's NSE dump."""
    for row in instruments:
        if row.get("segment") == KITE_SEGMENT_INDICES and row.get("tradingsymbol") == tradingsymbol:
            return int(row["instrument_token"])
    raise LookupError(f"{tradingsymbol!r} not found in the NSE instrument dump")


async def fetch_index_token(client: httpx.AsyncClient, tradingsymbol: str = NIFTY_TRADINGSYMBOL) -> int:
    response = await client.get(INSTRUMENTS_NSE_URL)
    response.raise_for_status()
    return find_index_token(list(csv.DictReader(io.StringIO(response.text))), tradingsymbol)


async def fetch_chunk(client: httpx.AsyncClient, token: int, start: date, end: date) -> list[Bar]:
    """One historical request. ``start``/``end`` inclusive; must be within Kite's 60-day cap."""
    response = await client.get(
        HISTORICAL_URL_TEMPLATE.format(token=token, interval=CANDLE_INTERVAL),
        params={"from": f"{start.isoformat()} 00:00:00", "to": f"{end.isoformat()} 23:59:59"},
    )
    response.raise_for_status()
    return parse_candles(response.json())


async def sync(
    db: Path = DEFAULT_CANDLE_DB,
    start: date = DEFAULT_HISTORY_START,
    end: date | None = None,
    token_db: Path | None = None,
    tradingsymbol: str = NIFTY_TRADINGSYMBOL,
) -> int:
    """Fetch every not-yet-cached chunk of [start, end]. Returns candles added."""
    end = end or datetime.now(IST).date()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    ensure_schema(conn)

    pending = missing_chunks(conn, start, end)
    if not pending:
        conn.close()
        return 0

    access = require_fresh_token(db=token_db)
    added = 0
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=_auth_headers(access)) as client:
        token = await fetch_index_token(client, tradingsymbol)
        for chunk_start, chunk_end in pending:
            bars = await fetch_chunk(client, token, chunk_start, chunk_end)
            store_candles(conn, bars)
            conn.execute(
                "INSERT OR REPLACE INTO fetch_chunks (from_date, to_date, candles, fetched_at)"
                " VALUES (?, ?, ?, ?)",
                (chunk_start.isoformat(), chunk_end.isoformat(), len(bars), datetime.now(IST).isoformat()),
            )
            conn.commit()
            added += len(bars)
            print(f"  {chunk_start} .. {chunk_end}: {len(bars):>6} candles")
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)

    conn.close()
    return added


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache NIFTY index minute candles from Kite (read only)")
    parser.add_argument("--db", type=Path, default=DEFAULT_CANDLE_DB, help="SQLite cache file")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, default=DEFAULT_HISTORY_START)
    parser.add_argument("--to", dest="end", type=date.fromisoformat, default=None)
    parser.add_argument("--token-db", type=Path, default=None, help="SQLite file holding the Kite access token")
    parser.add_argument("--symbol", default=NIFTY_TRADINGSYMBOL, help="index tradingsymbol in the NSE dump")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    added = asyncio.run(
        sync(db=args.db, start=args.start, end=args.end, token_db=args.token_db, tradingsymbol=args.symbol)
    )
    conn = sqlite3.connect(args.db)
    ensure_schema(conn)
    total, days = conn.execute("SELECT COUNT(*), COUNT(DISTINCT substr(ts, 1, 10)) FROM candles").fetchone()
    conn.close()
    print(f"added {added} candles; cache now holds {total} candles over {days} sessions -> {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
