"""Contract specifications for NSE index options — NIFTY and BANKNIFTY only.

Everything that NSE has revised over time is stored as a *date-keyed regime table* with the
governing circular cited inline, because a backtest that spans a revision must use the value
that was in force on the trade date, not today's value.

No other underlying is supported. Adding one requires adding its regimes here deliberately.

Primary sources
---------------
- Lot sizes (current): NSE circular NSE/FAOP/70616, Ref 176/2025, dated 03-Oct-2025,
  "Revision in Market Lot of Derivative Contracts on Indices", issued under
  SEBI/HO/MRD-PoD2/CIR/P/2024/00181 dated 30-Dec-2024.
  https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf
- Lot sizes (Apr-2025 revision): NSE revision effective 25-Apr-2025 announcement — BANKNIFTY
  30 -> 35, MIDCPNIFTY 120 -> 140; first reflected in the Jul-2025 monthly series.
- Lot sizes (Nov-2024 revision): NSE circular NSE/FAOP/64716 dated 25-Oct-2024, issued under
  SEBI/HO/MRD/MRD-PoD-3/P/CIR/2024/132 dated 01-Oct-2024 ("Measures to strengthen index
  derivatives framework") — minimum contract value raised to Rs 15 lakh.
- Tick size / strike scheme: NSE F&O contract master and the NIFTY / BANKNIFTY contract
  specifications published at https://www.nseindia.com/products-services/equity-derivatives-*
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

# ── Underlyings ──────────────────────────────────────────────────────────────────────────


class Index(str, Enum):
    """The only two underlyings this package supports."""

    NIFTY = "NIFTY"
    BANKNIFTY = "BANKNIFTY"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


# ── Tick size ────────────────────────────────────────────────────────────────────────────

# Rs 0.05 for index options on NSE. Unchanged across the 2024-2026 window covered here.
# Source: NSE equity-derivatives contract specifications (tick size Re 0.05).
TICK_SIZE: Decimal = Decimal("0.05")


# ── Strike intervals ─────────────────────────────────────────────────────────────────────

# Interval between adjacent strikes in the liquid near-the-money band.
# NIFTY: 50 points. BANKNIFTY: 100 points.
# NSE also lists a wider outer wing (BANKNIFTY strikes step to 500 far from spot); we only
# ever quote strikes inside the near band, so a single interval per index is sufficient and
# is deliberately the only thing encoded — see docs/options-paper-trading-plan.md Sec 1.1.
STRIKE_INTERVAL: dict[Index, int] = {
    Index.NIFTY: 50,
    Index.BANKNIFTY: 100,
}

# Outer-wing strike interval, recorded for documentation only; not used by strike selection.
WING_STRIKE_INTERVAL: dict[Index, int] = {
    Index.NIFTY: 100,
    Index.BANKNIFTY: 500,
}


# ── Lot size regimes ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LotSizeRegime:
    """A lot size that was in force for contracts trading on/after ``effective_from``."""

    effective_from: date
    lot_size: int
    source: str


# Regimes are ordered oldest-first. ``effective_from`` is the first *trading* date on which a
# contract carrying the new lot size could be dealt in, not the circular date.
#
# NIFTY history:
#   25 -> 75  : NSE/FAOP/64716 (25-Oct-2024) under SEBI cir. 01-Oct-2024. New weekly/monthly
#               contracts from 20-Nov-2024; existing monthlies revised at Nov-2024 expiry.
#   75 -> 65  : NSE/FAOP/70616 (03-Oct-2025). Weeklies from the 06-Jan-2026 contract;
#               monthlies from the 27-Jan-2026 expiry; quarterlies/half-yearlies revised at
#               the close of 30-Dec-2025. We key off 2025-12-31, the first trading day on
#               which any listed contract carried the new size.
LOT_SIZE_REGIMES: dict[Index, tuple[LotSizeRegime, ...]] = {
    Index.NIFTY: (
        LotSizeRegime(date(2000, 1, 1), 25, "pre-Nov-2024 baseline (NSE contract master)"),
        LotSizeRegime(date(2024, 11, 20), 75, "NSE/FAOP/64716 dated 25-Oct-2024"),
        LotSizeRegime(date(2025, 12, 31), 65, "NSE/FAOP/70616 (Ref 176/2025) dated 03-Oct-2025"),
    ),
    # BANKNIFTY history:
    #   15 -> 30 : NSE/FAOP/64716 (25-Oct-2024), effective with contracts from 20-Nov-2024.
    #   30 -> 35 : NSE lot-size revision effective 25-Apr-2025; existing Apr/May/Jun-2025
    #              monthlies kept the old size, so the first contracts actually carrying 35
    #              were the Jul-2025 series.
    #   35 -> 30 : NSE/FAOP/70616 (03-Oct-2025), same timeline as NIFTY above.
    Index.BANKNIFTY: (
        LotSizeRegime(date(2000, 1, 1), 15, "pre-Nov-2024 baseline (NSE contract master)"),
        LotSizeRegime(date(2024, 11, 20), 30, "NSE/FAOP/64716 dated 25-Oct-2024"),
        LotSizeRegime(date(2025, 4, 25), 35, "NSE lot revision effective 25-Apr-2025"),
        LotSizeRegime(date(2025, 12, 31), 30, "NSE/FAOP/70616 (Ref 176/2025) dated 03-Oct-2025"),
    ),
}


def lot_size(index: Index, on: date) -> int:
    """Lot size in force for ``index`` on trade date ``on``.

    Raises ``ValueError`` for dates before the earliest regime we have encoded.
    """
    regimes = LOT_SIZE_REGIMES[index]
    chosen: LotSizeRegime | None = None
    for regime in regimes:
        if on >= regime.effective_from:
            chosen = regime
    if chosen is None:
        raise ValueError(f"No lot-size regime encoded for {index.value} on {on.isoformat()}")
    return chosen.lot_size


def lot_size_source(index: Index, on: date) -> str:
    """Citation for the lot size returned by :func:`lot_size`."""
    regimes = LOT_SIZE_REGIMES[index]
    chosen: LotSizeRegime | None = None
    for regime in regimes:
        if on >= regime.effective_from:
            chosen = regime
    if chosen is None:
        raise ValueError(f"No lot-size regime encoded for {index.value} on {on.isoformat()}")
    return chosen.source


# ── Quantity freeze ──────────────────────────────────────────────────────────────────────

# Maximum quantity per order before the exchange freezes it for manual approval.
# The contract master publishes MaxTradQty as 1801 / 601; the effective freeze is one lot
# below, i.e. the largest order that will pass without a freeze.
# Source: NSE F&O contract master (MaxTradQty), cross-checked against
# docs/options-paper-trading-plan.md Sec 1.1 (verified 2026-08-28 against FAOP73928).
QUANTITY_FREEZE: dict[Index, int] = {
    Index.NIFTY: 1800,
    Index.BANKNIFTY: 600,
}


# ── Strike selection ─────────────────────────────────────────────────────────────────────


def atm_strike(index: Index, spot: float | Decimal) -> int:
    """Nearest listed strike to ``spot`` (at-the-money).

    Ties (spot exactly between two strikes) round *up*, matching the convention of taking the
    higher strike when NSE's chain is symmetric around spot.
    """
    interval = STRIKE_INTERVAL[index]
    spot_dec = Decimal(str(spot))
    # floor-divide then decide, so behaviour is exact rather than float-rounding dependent.
    lower = int(spot_dec // interval) * interval
    remainder = spot_dec - lower
    half = Decimal(interval) / 2
    return lower + interval if remainder >= half else lower


def strike_at_offset(index: Index, spot: float | Decimal, offset: int) -> int:
    """Strike ``offset`` steps away from ATM. Negative is below spot, positive above."""
    return atm_strike(index, spot) + offset * STRIKE_INTERVAL[index]


def is_valid_strike(index: Index, strike: int) -> bool:
    """True when ``strike`` sits on the near-band strike grid for ``index``."""
    return strike > 0 and strike % STRIKE_INTERVAL[index] == 0


# ── Tradingsymbol construction / parsing ─────────────────────────────────────────────────

# NSE index-option tradingsymbols (as used by NSE and by Zerodha's instrument dump) come in
# two shapes:
#
#   monthly : <NAME><YY><MMM><STRIKE><CE|PE>       e.g. NIFTY26JAN24800CE
#   weekly  : <NAME><YY><M><DD><STRIKE><CE|PE>     e.g. NIFTY26106 24800CE -> NIFTY2610624800CE
#
# In the weekly form the month is a single character: "1".."9" for Jan-Sep, then "O", "N", "D"
# for Oct, Nov, Dec. The day is always two digits.
_MONTH_ABBR: tuple[str, ...] = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)
_WEEKLY_MONTH_CODE: tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "O", "N", "D")

_MONTHLY_RE = re.compile(r"^(?P<name>NIFTY|BANKNIFTY)(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<strike>\d+)(?P<opt>CE|PE)$")
_WEEKLY_RE = re.compile(
    r"^(?P<name>NIFTY|BANKNIFTY)(?P<yy>\d{2})(?P<mon>[1-9OND])(?P<dd>\d{2})(?P<strike>\d+)(?P<opt>CE|PE)$"
)


def build_tradingsymbol(
    index: Index,
    expiry: date,
    strike: int,
    option_type: OptionType,
    *,
    is_monthly: bool,
) -> str:
    """Construct the NSE tradingsymbol for an index option.

    ``is_monthly`` must be supplied by the caller (from the expiry ladder in
    :mod:`app.options.calendar`) because the symbol format differs between the monthly and
    weekly series and cannot be inferred from the date alone.
    """
    yy = f"{expiry.year % 100:02d}"
    if is_monthly:
        return f"{index.value}{yy}{_MONTH_ABBR[expiry.month - 1]}{strike}{option_type.value}"
    return f"{index.value}{yy}{_WEEKLY_MONTH_CODE[expiry.month - 1]}{expiry.day:02d}{strike}{option_type.value}"


@dataclass(frozen=True)
class ParsedSymbol:
    """Decomposed NSE index-option tradingsymbol."""

    index: Index
    expiry_year: int
    expiry_month: int
    expiry_day: int | None  # None for monthly symbols, which do not encode a day
    strike: int
    option_type: OptionType
    is_monthly: bool


def parse_tradingsymbol(symbol: str) -> ParsedSymbol:
    """Parse an NSE index-option tradingsymbol.

    Monthly symbols do not encode the day of expiry, so ``expiry_day`` is ``None`` for them;
    resolve the actual date via :func:`app.options.calendar.monthly_expiry`.

    Raises ``ValueError`` if ``symbol`` is not a recognised NIFTY/BANKNIFTY option symbol.
    """
    text = symbol.strip().upper()

    monthly = _MONTHLY_RE.match(text)
    if monthly:
        mon = monthly.group("mon")
        if mon not in _MONTH_ABBR:
            raise ValueError(f"Unrecognised month abbreviation in tradingsymbol: {symbol!r}")
        return ParsedSymbol(
            index=Index(monthly.group("name")),
            expiry_year=2000 + int(monthly.group("yy")),
            expiry_month=_MONTH_ABBR.index(mon) + 1,
            expiry_day=None,
            strike=int(monthly.group("strike")),
            option_type=OptionType(monthly.group("opt")),
            is_monthly=True,
        )

    weekly = _WEEKLY_RE.match(text)
    if weekly:
        return ParsedSymbol(
            index=Index(weekly.group("name")),
            expiry_year=2000 + int(weekly.group("yy")),
            expiry_month=_WEEKLY_MONTH_CODE.index(weekly.group("mon")) + 1,
            expiry_day=int(weekly.group("dd")),
            strike=int(weekly.group("strike")),
            option_type=OptionType(weekly.group("opt")),
            is_monthly=False,
        )

    raise ValueError(f"Not a NIFTY/BANKNIFTY option tradingsymbol: {symbol!r}")
