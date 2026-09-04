"""Phase 0b live capture: 09:15–10:00 IST option-chain snapshots to SQLite — CAPTURE ONLY.

PAPER TRADING ONLY. This module reads exactly two Kite Connect endpoints — the NFO
instrument dump and the batched ``/quote`` endpoint — and writes rows to a local SQLite
file. It places, modifies and cancels nothing; no order endpoint is referenced and the
``kiteconnect`` SDK is deliberately not imported (see app.options.broker's docstring).

What it captures, per docs/options-paper-trading-plan.md Sec 10 Phase 0b: for NIFTY and
BANKNIFTY, full quotes (bid/ask with top-of-book size, LTP, volume, OI) for ATM+/-5 strikes
of every Sec-1.3-eligible expiry, plus the underlying spot and India VIX, every cycle. The
snapshot cadence is NOT specified by Sec 4 or Sec 10 of the plan; 5-second REST polling is
the v1 choice (see SNAPSHOT_INTERVAL_SECONDS). Every quote's exchange timestamp is stored so
the Sec 2.7 staleness gate can later be measured against real feed latency.

Trading-day gate: capture runs on every day :func:`app.options.calendar.is_trading_day`
accepts — weekends and NSE holidays are skipped, but expiry days and days failing the DTE>=5
rule are CAPTURED, deliberately: we would not trade them, but data is data (the plan's
Phase 0b wants spreads and latency measured, not trades simulated).

Compliance (plan doc Sec 6): this is the licensed broker feed the plan requires. Nothing
here touches nseindia.com.

Run (see deploy/RUNBOOK-capture.md)::

    python -m app.options.capture --db data/options/capture.db
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import sqlite3
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import httpx

from app.options import notify
from app.options.broker import (
    KITE_API_BASE,
    KITE_VERSION_HEADER,
    REQUEST_TIMEOUT_SECONDS,
    StoredToken,
    api_key,
    require_fresh_token,
)
from app.options.calendar import (
    IST,
    MIN_DTE,
    WINDOW_CLOSE,
    WINDOW_OPEN,
    dte,
    expiry_ladder,
    is_trading_day,
    now_ist,
)
from app.options.contracts import Index, OptionType, strike_at_offset

# ── Capture parameters ───────────────────────────────────────────────────────────────────

#: Seconds between snapshots. The plan doc (Sec 4 / Sec 10) specifies no cadence; 5-second
#: REST polling is the v1 choice. Kite's REST rate limit for /quote is 1 request/second with
#: up to 500 instruments per call (source: Kite Connect v3 docs, "Rate limits"), and one
#: batched call per cycle covers everything captured here, so this polls at 1/5th of the
#: permitted request rate.
SNAPSHOT_INTERVAL_SECONDS = 5.0

#: Kite /quote accepts up to this many instrument keys per call. Source: Kite Connect v3 docs.
QUOTE_MAX_INSTRUMENTS = 500

#: Strikes captured either side of ATM, per plan doc Sec 10 Phase 0b ("ATM+/-5").
ATM_STRIKE_SPAN = 5

#: Expiries captured per index: every ladder expiry passing the Sec 1.3 DTE>=5 rule, nearest
#: first, capped at this many. Two = the expiry we would trade plus the one we would roll to,
#: which bounds the instrument count while covering the roll boundary Sec 1.3's table walks.
MAX_EXPIRIES_PER_INDEX = 2

#: How far ahead to look for eligible expiries. 60 days always contains at least two monthly
#: expiries, so BANKNIFTY (monthly-only since 20-Nov-2024) still yields MAX_EXPIRIES_PER_INDEX.
EXPIRY_HORIZON_DAYS = 60

#: Hard exit for the capture process: WINDOW_CLOSE (10:00 IST) ends the last cycle, and the
#: process must be gone by 10:05 (flush + heartbeat grace) per the Phase 0b runbook / systemd
#: unit, which starts it at 09:00 and expects it to exit on its own.
CAPTURE_HARD_STOP: time = time(10, 5)

#: Kite instrument-dump and quote endpoints (read-only).
INSTRUMENTS_NFO_URL = KITE_API_BASE + "/instruments/NFO"
QUOTE_URL = KITE_API_BASE + "/quote"

#: Kite quote keys for the underlying spot indices and India VIX.
SPOT_KEYS: dict[Index, str] = {
    Index.NIFTY: "NSE:NIFTY 50",
    Index.BANKNIFTY: "NSE:NIFTY BANK",
}
VIX_KEY = "NSE:INDIA VIX"

#: Kite's instrument dump uses these values for index options rows.
KITE_SEGMENT_OPTIONS = "NFO-OPT"

DEFAULT_CAPTURE_DB = Path("data/options/capture.db")

CAPTURED_INDICES: tuple[Index, ...] = (Index.NIFTY, Index.BANKNIFTY)


# ── SQLite schema ────────────────────────────────────────────────────────────────────────

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS chain_snapshots (
    ts         TEXT    NOT NULL,  -- capture wall clock, IST ISO-8601
    index_name TEXT    NOT NULL,  -- NIFTY / BANKNIFTY
    expiry     TEXT    NOT NULL,  -- ISO date
    strike     INTEGER NOT NULL,
    opt_type   TEXT    NOT NULL,  -- CE / PE
    bid        REAL,              -- best bid (depth level 1); NULL when no bid exists
    ask        REAL,              -- best ask (depth level 1); NULL when no ask exists
    bid_qty    INTEGER,
    ask_qty    INTEGER,
    ltp        REAL,
    volume     INTEGER,
    oi         INTEGER,
    feed_ts    TEXT               -- exchange timestamp from the quote, for Sec 2.7 staleness
);
CREATE INDEX IF NOT EXISTS ix_chain_snapshots_key
    ON chain_snapshots (index_name, expiry, strike, opt_type, ts);

CREATE TABLE IF NOT EXISTS index_snapshots (
    ts      TEXT NOT NULL,
    symbol  TEXT NOT NULL,  -- NSE:NIFTY 50 / NSE:NIFTY BANK / NSE:INDIA VIX
    ltp     REAL,
    feed_ts TEXT
);
CREATE INDEX IF NOT EXISTS ix_index_snapshots_key ON index_snapshots (symbol, ts);

-- Plan doc loophole #15: a dead capture must be distinguishable from a quiet day.
CREATE TABLE IF NOT EXISTS heartbeats (
    ts     TEXT NOT NULL,
    event  TEXT NOT NULL,  -- start / cycle_error / end / skipped
    detail TEXT
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_DDL)


# ── Pure selection logic (unit-tested without any network) ──────────────────────────────


@dataclass(frozen=True)
class InstrumentMeta:
    """What we need to know about one option instrument to store its quotes."""

    quote_key: str  # e.g. "NFO:NIFTY26SEP24800CE"
    index: Index
    expiry: date
    strike: int
    opt_type: OptionType


def eligible_expiries(index: Index, on: date) -> list[date]:
    """Ladder expiries passing the Sec 1.3 DTE>=5 rule, nearest first, capped.

    Deliberately does NOT require ``on`` itself to be tradeable: capture runs on expiry days
    too, and the eligible expiries on such a day are simply the later ones.
    """
    ladder = expiry_ladder(index, on, on + timedelta(days=EXPIRY_HORIZON_DAYS))
    passing = [e for e in ladder if dte(on, e) >= MIN_DTE]
    return passing[:MAX_EXPIRIES_PER_INDEX]


def chain_strikes(index: Index, spot: float) -> list[int]:
    """ATM+/-ATM_STRIKE_SPAN strikes for ``index`` at ``spot``."""
    return [strike_at_offset(index, spot, offset) for offset in range(-ATM_STRIKE_SPAN, ATM_STRIKE_SPAN + 1)]


def select_chain_instruments(
    instruments: Iterable[dict[str, str]],
    index: Index,
    spot: float,
    expiries: Sequence[date],
) -> list[InstrumentMeta]:
    """Filter a Kite NFO instrument dump down to the option chain we capture.

    ``instruments`` rows are dicts with at least ``name``, ``segment``, ``expiry`` (ISO),
    ``strike``, ``instrument_type`` and ``tradingsymbol`` — the columns of Kite's CSV dump.
    """
    wanted_strikes = set(chain_strikes(index, spot))
    wanted_expiries = {e.isoformat() for e in expiries}
    selected: list[InstrumentMeta] = []
    for row in instruments:
        if row.get("segment") != KITE_SEGMENT_OPTIONS or row.get("name") != index.value:
            continue
        if row.get("expiry") not in wanted_expiries:
            continue
        if row.get("instrument_type") not in (OptionType.CE.value, OptionType.PE.value):
            continue
        strike = int(float(row["strike"]))
        if strike not in wanted_strikes:
            continue
        selected.append(
            InstrumentMeta(
                quote_key=f"NFO:{row['tradingsymbol']}",
                index=index,
                expiry=date.fromisoformat(row["expiry"]),
                strike=strike,
                opt_type=OptionType(row["instrument_type"]),
            )
        )
    return selected


def batch_keys(keys: Sequence[str], size: int = QUOTE_MAX_INSTRUMENTS) -> list[list[str]]:
    """Split quote keys into /quote-sized batches (Kite: max 500 instruments per call)."""
    if size <= 0:
        raise ValueError("batch size must be positive")
    return [list(keys[i : i + size]) for i in range(0, len(keys), size)]


def _depth_level(quote: dict, side: str) -> tuple[float | None, int | None]:  # type: ignore[type-arg]
    levels = quote.get("depth", {}).get(side, [])
    if not levels:
        return None, None
    top = levels[0]
    price = top.get("price")
    quantity = top.get("quantity")
    # Kite reports an absent book as price 0 / quantity 0 — store NULL, not a fake zero quote,
    # so the no-quote failure branch (plan doc Sec 2.5) is measurable from the archive.
    if not quantity:
        return None, None
    return float(price), int(quantity)


#: Any feed timestamp older than this is not a real quote time — Kite renders a missing
#: exchange timestamp as epoch zero ("1970-01-01 05:30:00" in IST). Stored verbatim it looks
#: like a 20-year-stale quote and destroys any average over feed_ts, so it becomes NULL.
FEED_TS_FLOOR = "2000-01-01"


def _feed_ts(quote: dict) -> str | None:  # type: ignore[type-arg]
    """Exchange quote timestamp, or NULL when the feed did not supply a usable one.

    Absent ("" / None) and epoch-zero timestamps both mean "unknown"; only NULL says that
    honestly. Compared as text, which is safe for Kite's zero-padded 'YYYY-MM-DD HH:MM:SS'.
    """
    raw = quote.get("timestamp")
    if not raw:
        return None
    value = str(raw).strip()
    if not value or value < FEED_TS_FLOOR:
        return None
    return value


def snapshot_rows(
    ts: datetime,
    quotes: dict[str, dict],  # type: ignore[type-arg]
    meta_by_key: dict[str, InstrumentMeta],
) -> list[
    tuple[str, str, str, int, str, float | None, float | None, int | None, int | None, float, int, int, str | None]
]:
    """Flatten a Kite /quote payload into chain_snapshots rows. Pure; unit-tested."""
    rows = []
    for key, meta in meta_by_key.items():
        quote = quotes.get(key)
        if quote is None:
            continue  # instrument absent from this response; visible as a gap in the archive
        bid, bid_qty = _depth_level(quote, "buy")
        ask, ask_qty = _depth_level(quote, "sell")
        rows.append(
            (
                ts.isoformat(),
                meta.index.value,
                meta.expiry.isoformat(),
                meta.strike,
                meta.opt_type.value,
                bid,
                ask,
                bid_qty,
                ask_qty,
                float(quote.get("last_price", 0.0)),
                int(quote.get("volume", 0)),
                int(quote.get("oi", 0)),
                _feed_ts(quote),
            )
        )
    return rows


def _expiry_summary(expiries: dict[Index, list[date]]) -> str:
    """One line of the day's captured expiries per index, for the start notification."""
    return "; ".join(
        f"{index.value} {', '.join(e.isoformat() for e in expiries[index]) or 'none'}" for index in CAPTURED_INDICES
    )


def should_capture(on: date) -> bool:
    """Capture on every NSE trading day — holiday/weekend gate ONLY.

    Deliberately not :func:`app.options.calendar.is_tradeable`: the DTE>=5 and expiry-day
    rules say when we would *trade*; spreads and latency are worth measuring every session.
    """
    return is_trading_day(on)


# ── Kite REST access (read-only) ─────────────────────────────────────────────────────────


def _auth_headers(token: StoredToken) -> dict[str, str]:
    return {**KITE_VERSION_HEADER, "Authorization": f"token {api_key()}:{token.access_token}"}


async def fetch_instrument_dump(client: httpx.AsyncClient) -> list[dict[str, str]]:
    """The day's NFO instrument dump (CSV -> list of dicts). One call per run."""
    response = await client.get(INSTRUMENTS_NFO_URL)
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.text)))


async def fetch_quotes(client: httpx.AsyncClient, keys: Sequence[str]) -> dict[str, dict]:  # type: ignore[type-arg]
    """Batched /quote fetch. Respects QUOTE_MAX_INSTRUMENTS; caller respects the 1 req/s limit."""
    merged: dict[str, dict] = {}  # type: ignore[type-arg]
    for batch in batch_keys(keys):
        response = await client.get(QUOTE_URL, params=[("i", key) for key in batch])
        response.raise_for_status()
        merged.update(response.json().get("data", {}))
    return merged


# ── Capture loop ─────────────────────────────────────────────────────────────────────────


def _heartbeat(conn: sqlite3.Connection, event: str, detail: str = "") -> None:
    conn.execute("INSERT INTO heartbeats (ts, event, detail) VALUES (?, ?, ?)", (now_ist().isoformat(), event, detail))
    conn.commit()


async def _sleep_until(target: datetime) -> None:
    remaining = (target - now_ist()).total_seconds()
    if remaining > 0:
        await asyncio.sleep(remaining)


async def run_capture(db: Path = DEFAULT_CAPTURE_DB, token_db: Path | None = None) -> int:
    """One session's capture. Returns the number of snapshot cycles completed.

    Exits immediately (with a 'skipped' heartbeat) on non-trading days; otherwise waits for
    WINDOW_OPEN, snapshots every SNAPSHOT_INTERVAL_SECONDS until WINDOW_CLOSE, and is gone
    well before CAPTURE_HARD_STOP.
    """
    today = now_ist().date()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    ensure_schema(conn)

    if not should_capture(today):
        _heartbeat(conn, "skipped", f"{today.isoformat()} is not an NSE trading day")
        conn.close()
        return 0

    token = require_fresh_token(db=token_db)
    open_dt = datetime.combine(today, WINDOW_OPEN, tzinfo=IST)
    close_dt = datetime.combine(today, WINDOW_CLOSE, tzinfo=IST)
    hard_stop = datetime.combine(today, CAPTURE_HARD_STOP, tzinfo=IST)

    cycles = 0
    chain_rows = 0
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=_auth_headers(token)) as client:
        await _sleep_until(open_dt)
        _heartbeat(conn, "start", f"window {WINDOW_OPEN}-{WINDOW_CLOSE}")

        instruments = await fetch_instrument_dump(client)
        expiries = {index: eligible_expiries(index, today) for index in CAPTURED_INDICES}
        notify.send(f"▶️ Capture started {today.isoformat()}, expiries: {_expiry_summary(expiries)}", heartbeat_db=db)
        spot_keys = [SPOT_KEYS[index] for index in CAPTURED_INDICES] + [VIX_KEY]
        meta_by_key: dict[str, InstrumentMeta] = {}

        while now_ist() < close_dt and now_ist() < hard_stop:
            cycle_started = now_ist()
            try:
                spot_quotes = await fetch_quotes(client, spot_keys)
                for index in CAPTURED_INDICES:
                    spot_quote = spot_quotes.get(SPOT_KEYS[index], {})
                    spot = float(spot_quote.get("last_price", 0.0))
                    if spot > 0:
                        # Re-select around the latest spot so ATM drift keeps the +/-5 window
                        # centred; union with prior selections keeps earlier strikes flowing.
                        for meta in select_chain_instruments(instruments, index, spot, expiries[index]):
                            meta_by_key.setdefault(meta.quote_key, meta)
                conn.executemany(
                    "INSERT INTO index_snapshots (ts, symbol, ltp, feed_ts) VALUES (?, ?, ?, ?)",
                    [
                        (
                            cycle_started.isoformat(),
                            key,
                            float(spot_quotes.get(key, {}).get("last_price", 0.0)),
                            _feed_ts(spot_quotes.get(key, {})),
                        )
                        for key in spot_keys
                    ],
                )
                if meta_by_key:
                    chain_quotes = await fetch_quotes(client, list(meta_by_key))
                    rows = snapshot_rows(cycle_started, chain_quotes, meta_by_key)
                    conn.executemany(
                        "INSERT INTO chain_snapshots (ts, index_name, expiry, strike, opt_type, bid, ask,"
                        " bid_qty, ask_qty, ltp, volume, oi, feed_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        rows,
                    )
                    chain_rows += len(rows)
                conn.commit()
                cycles += 1
            except (httpx.HTTPError, sqlite3.Error, ValueError) as exc:  # keep capturing; log it
                _heartbeat(conn, "cycle_error", f"{type(exc).__name__}: {exc}")
            await _sleep_until(cycle_started + timedelta(seconds=SNAPSHOT_INTERVAL_SECONDS))

    _heartbeat(conn, "end", f"{cycles} cycles")
    notify.send(
        f"✔️ Capture done: {cycles} cycles, {chain_rows} rows, "
        f"{'/'.join(index.value for index in CAPTURED_INDICES)}, window {WINDOW_OPEN:%H:%M}–{WINDOW_CLOSE:%H:%M}",
        heartbeat_db=db,
    )
    conn.close()
    return cycles


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 0b capture: 09:15-10:00 IST chain snapshots (capture only)")
    parser.add_argument("--db", type=Path, default=DEFAULT_CAPTURE_DB, help="SQLite file for snapshots")
    parser.add_argument("--token-db", type=Path, default=None, help="SQLite file holding the Kite access token")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        cycles = asyncio.run(run_capture(db=args.db, token_db=args.token_db))
    except Exception as exc:
        # Best-effort push before the crash surfaces in journald; the unit's OnFailure=
        # notifier is the backstop for deaths this line cannot see (OOM kill, SIGKILL).
        reason = f"{type(exc).__name__}: {exc}"
        notify.send(f"❌ Capture failed: {reason[:300]}", heartbeat_db=args.db)
        raise
    print(f"capture finished: {cycles} cycles -> {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
