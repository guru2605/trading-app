"""Tests for app.options.capture — Phase 0b chain-snapshot capture.

Pure-logic tests only: schema, instrument selection, batching, quote flattening, the
trading-day gate, and the capture-only constraint audit. No test touches the network; the
one HTTP helper exercised (``fetch_quotes``) runs against ``httpx.MockTransport``.
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

from app.options.calendar import (
    IST,
    MIN_DTE,
    NSE_HOLIDAYS,
    WINDOW_CLOSE,
    dte,
    is_tradeable,
    is_trading_day,
)
from app.options.capture import (
    ATM_STRIKE_SPAN,
    CAPTURE_HARD_STOP,
    CAPTURED_INDICES,
    MAX_EXPIRIES_PER_INDEX,
    QUOTE_MAX_INSTRUMENTS,
    SNAPSHOT_INTERVAL_SECONDS,
    SPOT_KEYS,
    VIX_KEY,
    InstrumentMeta,
    batch_keys,
    chain_strikes,
    eligible_expiries,
    ensure_schema,
    fetch_quotes,
    select_chain_instruments,
    should_capture,
    snapshot_rows,
)
from app.options.contracts import Index, OptionType

# ── Capture parameters ───────────────────────────────────────────────────────────────────


def test_cadence_respects_kite_rest_limits() -> None:
    # Kite REST: 1 req/s for /quote, 500 instruments per call. One batched call per cycle.
    assert SNAPSHOT_INTERVAL_SECONDS >= 1.0
    worst_case_instruments = (2 * ATM_STRIKE_SPAN + 1) * 2 * MAX_EXPIRIES_PER_INDEX * len(CAPTURED_INDICES)
    assert worst_case_instruments + len(SPOT_KEYS) + 1 <= QUOTE_MAX_INSTRUMENTS


def test_hard_stop_is_after_the_capture_window() -> None:
    assert CAPTURE_HARD_STOP > WINDOW_CLOSE


def test_capture_covers_exactly_the_two_plan_indices() -> None:
    assert set(CAPTURED_INDICES) == {Index.NIFTY, Index.BANKNIFTY}
    assert set(SPOT_KEYS) == {Index.NIFTY, Index.BANKNIFTY}
    assert VIX_KEY == "NSE:INDIA VIX"


# ── Schema ───────────────────────────────────────────────────────────────────────────────


def test_schema_creates_the_three_tables_and_round_trips_a_row() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"chain_snapshots", "index_snapshots", "heartbeats"} <= tables

    conn.execute(
        "INSERT INTO chain_snapshots (ts, index_name, expiry, strike, opt_type, bid, ask,"
        " bid_qty, ask_qty, ltp, volume, oi, feed_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "2026-08-28T09:15:00+05:30",
            "NIFTY",
            "2026-09-08",
            24800,
            "CE",
            145.5,
            146.2,
            75,
            150,
            145.9,
            1200,
            50000,
            "",
        ),
    )
    row = conn.execute("SELECT index_name, strike, opt_type, bid, ask FROM chain_snapshots").fetchone()
    assert row == ("NIFTY", 24800, "CE", 145.5, 146.2)


def test_schema_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    ensure_schema(conn)  # CREATE IF NOT EXISTS throughout


# ── Strike and instrument selection ──────────────────────────────────────────────────────


def test_chain_strikes_are_atm_plus_minus_span() -> None:
    strikes = chain_strikes(Index.NIFTY, 24812.0)  # ATM 24800
    assert len(strikes) == 2 * ATM_STRIKE_SPAN + 1
    assert strikes[0] == 24800 - ATM_STRIKE_SPAN * 50
    assert strikes[-1] == 24800 + ATM_STRIKE_SPAN * 50
    assert 24800 in strikes


def _dump_row(name: str, expiry: str, strike: int, opt_type: str, segment: str = "NFO-OPT") -> dict[str, str]:
    symbol = f"{name}TEST{strike}{opt_type}"
    return {
        "tradingsymbol": symbol,
        "name": name,
        "segment": segment,
        "expiry": expiry,
        "strike": str(float(strike)),
        "instrument_type": opt_type,
    }


def test_select_chain_instruments_filters_the_dump() -> None:
    expiry = date(2026, 9, 8)
    dump = []
    for strike in range(24000, 25700, 50):  # far wider than ATM +/- 5
        for opt_type in ("CE", "PE"):
            dump.append(_dump_row("NIFTY", expiry.isoformat(), strike, opt_type))
    # Distractors: wrong underlying, wrong segment, wrong expiry, futures row.
    dump.append(_dump_row("FINNIFTY", expiry.isoformat(), 24800, "CE"))
    dump.append(_dump_row("NIFTY", expiry.isoformat(), 24800, "FUT", segment="NFO-FUT"))
    dump.append(_dump_row("NIFTY", "2026-12-29", 24800, "CE"))

    selected = select_chain_instruments(dump, Index.NIFTY, spot=24812.0, expiries=[expiry])
    assert len(selected) == (2 * ATM_STRIKE_SPAN + 1) * 2  # 11 strikes x CE/PE
    assert all(meta.index is Index.NIFTY for meta in selected)
    assert all(meta.expiry == expiry for meta in selected)
    assert all(meta.quote_key.startswith("NFO:") for meta in selected)
    assert {meta.opt_type for meta in selected} == {OptionType.CE, OptionType.PE}
    assert min(meta.strike for meta in selected) == 24800 - ATM_STRIKE_SPAN * 50
    assert max(meta.strike for meta in selected) == 24800 + ATM_STRIKE_SPAN * 50


def test_select_chain_instruments_handles_multiple_expiries() -> None:
    expiries = [date(2026, 9, 8), date(2026, 9, 15)]
    dump = [
        _dump_row("NIFTY", e.isoformat(), strike, opt_type)
        for e in expiries
        for strike in range(24550, 25100, 50)
        for opt_type in ("CE", "PE")
    ]
    selected = select_chain_instruments(dump, Index.NIFTY, spot=24800.0, expiries=expiries)
    assert len(selected) == (2 * ATM_STRIKE_SPAN + 1) * 2 * 2


# ── Batching ─────────────────────────────────────────────────────────────────────────────


def test_batch_keys_respects_the_500_instrument_limit() -> None:
    keys = [f"NFO:X{i}" for i in range(1200)]
    batches = batch_keys(keys)
    assert [len(b) for b in batches] == [500, 500, 200]
    assert [k for batch in batches for k in batch] == keys


def test_batch_keys_rejects_a_nonsense_size() -> None:
    with pytest.raises(ValueError):
        batch_keys(["NFO:X"], size=0)


async def test_fetch_quotes_batches_and_merges(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys = request.url.params.get_list("i")
        calls.append(len(keys))
        return httpx.Response(200, json={"data": {k: {"last_price": 1.0} for k in keys}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quotes = await fetch_quotes(client, [f"NFO:X{i}" for i in range(700)])
    assert calls == [500, 200]
    assert len(quotes) == 700


# ── Quote flattening ─────────────────────────────────────────────────────────────────────


def _meta(key: str = "NFO:NIFTYTEST24800CE") -> InstrumentMeta:
    return InstrumentMeta(
        quote_key=key, index=Index.NIFTY, expiry=date(2026, 9, 8), strike=24800, opt_type=OptionType.CE
    )


def test_snapshot_rows_flatten_a_kite_quote() -> None:
    ts = datetime(2026, 8, 28, 9, 20, 5, tzinfo=IST)
    quotes = {
        "NFO:NIFTYTEST24800CE": {
            "last_price": 145.9,
            "volume": 1200,
            "oi": 50000,
            "timestamp": "2026-08-28 09:20:04",
            "depth": {
                "buy": [{"price": 145.5, "quantity": 75}, {"price": 145.4, "quantity": 150}],
                "sell": [{"price": 146.2, "quantity": 150}],
            },
        }
    }
    rows = snapshot_rows(ts, quotes, {"NFO:NIFTYTEST24800CE": _meta()})
    assert len(rows) == 1
    row = rows[0]
    assert row[1:5] == ("NIFTY", "2026-09-08", 24800, "CE")
    assert row[5:9] == (145.5, 146.2, 75, 150)  # top of book only
    assert row[9:12] == (145.9, 1200, 50000)
    assert row[12] == "2026-08-28 09:20:04"  # feed timestamp kept for the Sec 2.7 staleness gate


def test_snapshot_rows_store_an_empty_book_as_null_not_zero() -> None:
    # Kite reports an absent book as price 0 / quantity 0; a fake zero quote would poison the
    # Sec 2.5 no-quote measurement, so both must come out as NULL.
    ts = datetime(2026, 8, 28, 9, 15, 1, tzinfo=IST)
    quotes = {
        "NFO:NIFTYTEST24800CE": {
            "last_price": 145.9,
            "volume": 0,
            "oi": 50000,
            "timestamp": "",
            "depth": {"buy": [{"price": 0, "quantity": 0}], "sell": []},
        }
    }
    (row,) = snapshot_rows(ts, quotes, {"NFO:NIFTYTEST24800CE": _meta()})
    assert row[5] is None and row[7] is None  # zero-quantity bid -> NULL
    assert row[6] is None and row[8] is None  # missing ask depth -> NULL


def test_snapshot_rows_skip_instruments_absent_from_the_response() -> None:
    ts = datetime(2026, 8, 28, 9, 15, 1, tzinfo=IST)
    assert snapshot_rows(ts, {}, {"NFO:NIFTYTEST24800CE": _meta()}) == []


# ── Eligible expiries and the trading-day gate ───────────────────────────────────────────


def test_eligible_expiries_apply_the_dte_rule() -> None:
    on = date(2026, 6, 1)  # Sec 1.3 row: nearest expiry 2026-06-02 (DTE 1) must be skipped
    chosen = eligible_expiries(Index.NIFTY, on)
    assert 0 < len(chosen) <= MAX_EXPIRIES_PER_INDEX
    assert chosen == sorted(chosen)
    assert all(dte(on, e) >= MIN_DTE for e in chosen)
    assert date(2026, 6, 2) not in chosen
    assert chosen[0] == date(2026, 6, 9)


def test_eligible_expiries_work_on_an_expiry_day_too() -> None:
    # Capture runs on expiry day; the eligible expiries are simply the later ones.
    on = date(2026, 6, 2)
    chosen = eligible_expiries(Index.NIFTY, on)
    assert chosen and all(dte(on, e) >= MIN_DTE for e in chosen)


def test_banknifty_still_yields_eligible_expiries() -> None:
    # Monthly-only since 20-Nov-2024; the 60-day horizon must still find some.
    chosen = eligible_expiries(Index.BANKNIFTY, date(2026, 6, 1))
    assert chosen


def test_capture_gate_is_the_holiday_gate_not_the_trading_gate() -> None:
    # A trading day that is NOT tradeable (expiry day, Sec 1 rule) is still captured:
    # data is data. 2026-06-02 is the Sec 1.3 table's expiry Tuesday.
    expiry_tuesday = date(2026, 6, 2)
    assert is_trading_day(expiry_tuesday)
    assert not is_tradeable(expiry_tuesday, Index.NIFTY)
    assert should_capture(expiry_tuesday) is True


def test_capture_skips_weekends_and_holidays() -> None:
    assert should_capture(date(2026, 6, 6)) is False  # Saturday
    assert should_capture(date(2026, 6, 7)) is False  # Sunday
    weekday_holidays = [d for d in NSE_HOLIDAYS if d.year == 2026 and d.weekday() < 5]
    assert weekday_holidays, "expected at least one weekday NSE holiday in 2026"
    for holiday in weekday_holidays:
        assert should_capture(holiday) is False


# ── Capture-only constraint audit ────────────────────────────────────────────────────────

# No order-placement code path may exist anywhere in app/options — not even commented out.
FORBIDDEN_SOURCE_STRINGS = (
    "place_order",
    "order_place",
    "modify_order",
    "cancel_order",
    "basket_order",
    "place_gtt",
    "import kiteconnect",
    "from kiteconnect",
)


def test_no_order_write_api_is_referenced() -> None:
    package_dir = Path(__file__).resolve().parent.parent / "app" / "options"
    sources = sorted(package_dir.glob("*.py"))
    assert sources, f"expected package sources under {package_dir}"
    # Every broker-touching module must be in the sweep — a rename must fail here, loudly.
    names = {source.name for source in sources}
    assert {"broker.py", "capture.py", "autologin.py", "notify.py"} <= names, f"audit sweep is missing files: {names}"
    for source in sources:
        text = source.read_text()
        for forbidden in FORBIDDEN_SOURCE_STRINGS:
            assert forbidden not in text, f"{source.name} references forbidden API string {forbidden!r}"
