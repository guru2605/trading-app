"""Tests for app.options.contracts — NIFTY / BANKNIFTY contract specifications."""

from datetime import date
from decimal import Decimal

import pytest

from app.options.contracts import (
    LOT_SIZE_REGIMES,
    QUANTITY_FREEZE,
    STRIKE_INTERVAL,
    TICK_SIZE,
    Index,
    OptionType,
    atm_strike,
    build_tradingsymbol,
    is_valid_strike,
    lot_size,
    lot_size_source,
    parse_tradingsymbol,
    strike_at_offset,
)

# ── Static specs ─────────────────────────────────────────────────────────────────────────


def test_only_two_underlyings_are_supported() -> None:
    assert {ix.value for ix in Index} == {"NIFTY", "BANKNIFTY"}


def test_tick_size_is_five_paisa() -> None:
    # as_tuple() rather than == so the exponent is pinned too: Decimal("0.050") would compare
    # equal but is not what the contract master publishes.
    assert TICK_SIZE.as_tuple() == Decimal("0.05").as_tuple()


def test_strike_intervals() -> None:
    assert STRIKE_INTERVAL[Index.NIFTY] == 50
    assert STRIKE_INTERVAL[Index.BANKNIFTY] == 100


def test_quantity_freeze_matches_contract_master() -> None:
    # Contract master publishes MaxTradQty 1801 / 601; the freeze is the largest order that
    # passes, i.e. one below. See docs/options-paper-trading-plan.md Sec 1.1.
    assert QUANTITY_FREEZE[Index.NIFTY] == 1800
    assert QUANTITY_FREEZE[Index.BANKNIFTY] == 600


# ── Lot size regimes ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("index", "on", "expected"),
    [
        # Pre-Nov-2024 baseline.
        (Index.NIFTY, date(2024, 11, 19), 25),
        (Index.BANKNIFTY, date(2024, 11, 19), 15),
        # NSE/FAOP/64716 — minimum contract value raised to Rs 15 lakh.
        (Index.NIFTY, date(2024, 11, 20), 75),
        (Index.BANKNIFTY, date(2024, 11, 20), 30),
        (Index.NIFTY, date(2025, 6, 30), 75),
        # BANKNIFTY 30 -> 35 effective 25-Apr-2025 (NIFTY unchanged by that revision).
        (Index.BANKNIFTY, date(2025, 4, 24), 30),
        (Index.BANKNIFTY, date(2025, 4, 25), 35),
        (Index.BANKNIFTY, date(2025, 12, 30), 35),
        # NSE/FAOP/70616 — current sizes.
        (Index.NIFTY, date(2025, 12, 31), 65),
        (Index.BANKNIFTY, date(2025, 12, 31), 30),
        (Index.NIFTY, date(2026, 8, 28), 65),
        (Index.BANKNIFTY, date(2026, 8, 28), 30),
    ],
)
def test_lot_size_is_date_keyed(index: Index, on: date, expected: int) -> None:
    assert lot_size(index, on) == expected


def test_lot_size_regimes_are_ordered_and_sourced() -> None:
    for index, regimes in LOT_SIZE_REGIMES.items():
        dates = [r.effective_from for r in regimes]
        assert dates == sorted(dates), f"{index.value} regimes are not oldest-first"
        for regime in regimes:
            assert regime.source.strip(), f"{index.value} regime {regime.effective_from} has no source"


def test_lot_size_source_is_returned_for_the_regime_in_force() -> None:
    assert "70616" in lot_size_source(Index.NIFTY, date(2026, 8, 28))
    assert "64716" in lot_size_source(Index.NIFTY, date(2025, 1, 15))


def test_lot_size_rejects_dates_before_the_earliest_regime() -> None:
    with pytest.raises(ValueError, match="No lot-size regime"):
        lot_size(Index.NIFTY, date(1999, 1, 1))


# ── Strike selection ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("index", "spot", "expected"),
    [
        (Index.NIFTY, 24812.35, 24800),
        (Index.NIFTY, 24826.0, 24850),
        (Index.NIFTY, 24800.0, 24800),
        (Index.NIFTY, 24825.0, 24850),  # exact tie rounds up
        (Index.BANKNIFTY, 54049.0, 54000),
        (Index.BANKNIFTY, 54050.0, 54100),  # exact tie rounds up
        (Index.BANKNIFTY, 54081.7, 54100),
    ],
)
def test_atm_strike(index: Index, spot: float, expected: int) -> None:
    assert atm_strike(index, spot) == expected


def test_atm_strike_accepts_decimal_without_float_error() -> None:
    assert atm_strike(Index.NIFTY, Decimal("24825")) == 24850


@pytest.mark.parametrize(
    ("index", "spot", "offset", "expected"),
    [
        (Index.NIFTY, 24812.35, 0, 24800),
        (Index.NIFTY, 24812.35, 2, 24900),
        (Index.NIFTY, 24812.35, -3, 24650),
        (Index.BANKNIFTY, 54049.0, 1, 54100),
        (Index.BANKNIFTY, 54049.0, -2, 53800),
    ],
)
def test_strike_at_offset(index: Index, spot: float, offset: int, expected: int) -> None:
    assert strike_at_offset(index, spot, offset) == expected


def test_is_valid_strike() -> None:
    assert is_valid_strike(Index.NIFTY, 24800)
    assert not is_valid_strike(Index.NIFTY, 24825)
    assert is_valid_strike(Index.BANKNIFTY, 54100)
    assert not is_valid_strike(Index.BANKNIFTY, 54050)
    assert not is_valid_strike(Index.NIFTY, 0)
    assert not is_valid_strike(Index.NIFTY, -50)


# ── Tradingsymbols ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("index", "expiry", "strike", "opt", "monthly", "expected"),
    [
        (Index.NIFTY, date(2026, 1, 27), 24800, OptionType.CE, True, "NIFTY26JAN24800CE"),
        (Index.BANKNIFTY, date(2026, 1, 27), 54100, OptionType.PE, True, "BANKNIFTY26JAN54100PE"),
        # Weekly month codes: 1-9 for Jan-Sep, then O, N, D.
        (Index.NIFTY, date(2026, 1, 6), 24800, OptionType.CE, False, "NIFTY2610624800CE"),
        (Index.NIFTY, date(2026, 9, 8), 25000, OptionType.PE, False, "NIFTY2690825000PE"),
        (Index.NIFTY, date(2026, 10, 6), 25000, OptionType.CE, False, "NIFTY26O0625000CE"),
        (Index.NIFTY, date(2026, 11, 3), 25000, OptionType.CE, False, "NIFTY26N0325000CE"),
        (Index.NIFTY, date(2026, 12, 1), 25000, OptionType.CE, False, "NIFTY26D0125000CE"),
    ],
)
def test_build_tradingsymbol(
    index: Index, expiry: date, strike: int, opt: OptionType, monthly: bool, expected: str
) -> None:
    assert build_tradingsymbol(index, expiry, strike, opt, is_monthly=monthly) == expected


def test_parse_monthly_tradingsymbol() -> None:
    parsed = parse_tradingsymbol("NIFTY26JAN24800CE")
    assert parsed.index is Index.NIFTY
    assert parsed.expiry_year == 2026
    assert parsed.expiry_month == 1
    assert parsed.expiry_day is None  # monthly symbols do not encode the day
    assert parsed.strike == 24800
    assert parsed.option_type is OptionType.CE
    assert parsed.is_monthly


def test_parse_weekly_tradingsymbol() -> None:
    parsed = parse_tradingsymbol("NIFTY26O0625000PE")
    assert parsed.index is Index.NIFTY
    assert parsed.expiry_year == 2026
    assert parsed.expiry_month == 10
    assert parsed.expiry_day == 6
    assert parsed.strike == 25000
    assert parsed.option_type is OptionType.PE
    assert not parsed.is_monthly


@pytest.mark.parametrize(
    ("index", "expiry", "strike", "opt", "monthly"),
    [
        (Index.NIFTY, date(2026, 1, 27), 24800, OptionType.CE, True),
        (Index.BANKNIFTY, date(2026, 3, 31), 54100, OptionType.PE, True),
        (Index.NIFTY, date(2026, 1, 6), 24800, OptionType.CE, False),
        (Index.NIFTY, date(2026, 12, 29), 25500, OptionType.PE, False),
    ],
)
def test_build_then_parse_roundtrips(index: Index, expiry: date, strike: int, opt: OptionType, monthly: bool) -> None:
    parsed = parse_tradingsymbol(build_tradingsymbol(index, expiry, strike, opt, is_monthly=monthly))
    assert parsed.index is index
    assert parsed.expiry_year == expiry.year
    assert parsed.expiry_month == expiry.month
    assert parsed.strike == strike
    assert parsed.option_type is opt
    assert parsed.is_monthly is monthly
    if not monthly:
        assert parsed.expiry_day == expiry.day


@pytest.mark.parametrize(
    "symbol",
    [
        "RELIANCE26JAN2800CE",  # not an index we support
        "FINNIFTY26JAN24800CE",  # deliberately unsupported underlying
        "NIFTY26JAN24800XX",  # bad option type
        "NIFTY26XYZ24800CE",  # bad month abbreviation
        "",
        "NIFTY",
    ],
)
def test_parse_rejects_unsupported_symbols(symbol: str) -> None:
    with pytest.raises(ValueError):
        parse_tradingsymbol(symbol)


def test_parse_is_case_and_whitespace_insensitive() -> None:
    assert parse_tradingsymbol("  nifty26jan24800ce  ").strike == 24800
