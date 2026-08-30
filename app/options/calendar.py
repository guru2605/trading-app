"""NSE trading calendar, session bounds and index-option expiry ladder.

Every datetime this module produces is timezone-aware in ``Asia/Kolkata``. Naive datetimes are
never returned and never accepted as an intent to mean IST.

Sources
-------
Trading holidays
    NSE publishes the trading-holiday list annually by circular; the lists below were
    cross-checked against two independent public mirrors for each year because the NSE
    circular PDFs are not reliably fetchable (see the CONFIDENCE notes on each list).
    - 2024: NSE circular NSE/CMTR/59722 dated 12-Dec-2023, plus the two special holidays added
      in-year (22-Jan-2024 Ram Mandir Pran Pratishtha; 20-May-2024 Maharashtra general
      election, NSE/CMTR/61518).
    - 2025: NSE circulars NSE/CMTR/65587 and NSE/FAOP/65588.
    - 2026: NSE annual trading-holiday circular for calendar year 2026.

Expiry weekday
    NSE circular NSE/FAOP/68747 (Ref 111/2025) dated 25-Jun-2025 moved every NIFTY/BANKNIFTY/
    FINNIFTY/MIDCPNIFTY/NIFTYNXT50 expiry from Thursday to Tuesday, applicable to contracts
    expiring on or after 01-Sep-2025. Monthly/quarterly/half-yearly moved from the last
    Thursday to the last Tuesday of the expiry month on the same date.

BANKNIFTY weekly discontinuation
    SEBI circular SEBI/HO/MRD/MRD-PoD-3/P/CIR/2024/132 dated 01-Oct-2024 limited each exchange
    to one weekly index-option benchmark. NSE retained NIFTY; BANKNIFTY (and FINNIFTY,
    MIDCPNIFTY, NIFTYNXT50) weeklies stopped being issued from 20-Nov-2024.

Session timings
    NSE extended the *equity derivatives* close from 15:30 to 15:40 IST effective 03-Aug-2026,
    alongside the introduction of the Closing Auction Session. The cash/spot segment still
    closes at 15:30. Pre-open (09:00-09:08) is unchanged.

Session length is therefore 385 minutes (09:15 to 15:40), not 375. See
docs/options-paper-trading-plan.md Sec 8 — 375 was a documented Rev 1 error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.options.contracts import Index

# ── Timezone ─────────────────────────────────────────────────────────────────────────────

#: The one and only timezone this package reasons in.
IST = ZoneInfo("Asia/Kolkata")


# ── Session bounds ───────────────────────────────────────────────────────────────────────

#: Continuous trading starts at 09:15 IST (unchanged since 2010).
SESSION_OPEN: time = time(9, 15)

#: Equity-derivatives close, 15:40 IST, effective 03-Aug-2026 (Closing Auction Session change).
SESSION_CLOSE: time = time(15, 40)

#: The close that applied to equity derivatives *before* 03-Aug-2026.
SESSION_CLOSE_LEGACY: time = time(15, 30)

#: First trading date on which the 15:40 derivatives close applied.
SESSION_CLOSE_EXTENSION_DATE: date = date(2026, 8, 3)

#: Minutes in a full equity-derivatives session under the current 09:15-15:40 timings.
SESSION_MINUTES: int = 385

#: Minutes in a full session under the pre-03-Aug-2026 09:15-15:30 timings.
SESSION_MINUTES_LEGACY: int = 375

#: Entry-scan window: the strategy only opens positions between 09:15 and 10:00 IST.
WINDOW_OPEN: time = time(9, 15)
WINDOW_CLOSE: time = time(10, 0)


def session_close_time(on: date) -> time:
    """Equity-derivatives closing time in force on ``on``."""
    return SESSION_CLOSE if on >= SESSION_CLOSE_EXTENSION_DATE else SESSION_CLOSE_LEGACY


def session_minutes(on: date) -> int:
    """Length of the continuous equity-derivatives session on ``on``, in minutes."""
    return SESSION_MINUTES if on >= SESSION_CLOSE_EXTENSION_DATE else SESSION_MINUTES_LEGACY


def session_bounds(on: date) -> tuple[datetime, datetime]:
    """(open, close) as timezone-aware ``Asia/Kolkata`` datetimes for the session on ``on``."""
    return (
        datetime.combine(on, SESSION_OPEN, tzinfo=IST),
        datetime.combine(on, session_close_time(on), tzinfo=IST),
    )


def entry_window_bounds(on: date) -> tuple[datetime, datetime]:
    """(start, end) of the 09:15-10:00 IST entry window on ``on``, timezone-aware."""
    return (
        datetime.combine(on, WINDOW_OPEN, tzinfo=IST),
        datetime.combine(on, WINDOW_CLOSE, tzinfo=IST),
    )


def now_ist() -> datetime:
    """Current time as a timezone-aware ``Asia/Kolkata`` datetime."""
    return datetime.now(IST)


def to_ist(moment: datetime) -> datetime:
    """Convert an aware datetime to IST. Rejects naive datetimes rather than guessing."""
    if moment.tzinfo is None:
        raise ValueError("Naive datetime passed to to_ist(); attach a timezone explicitly")
    return moment.astimezone(IST)


# ── Trading holidays ─────────────────────────────────────────────────────────────────────

# CONFIDENCE: high. Base list from NSE/CMTR/59722 (12-Dec-2023) plus the two special holidays
# declared in-year. 22-Jan-2024 (Ram Mandir Pran Pratishtha) and 20-May-2024 (Maharashtra
# general election, NSE/CMTR/61518) were not in the original annual circular.
# 01-Nov-2024 was a holiday for the normal session; the Muhurat session traded that evening.
_HOLIDAYS_2024: frozenset[date] = frozenset(
    {
        date(2024, 1, 22),  # Special holiday - Ram Mandir Pran Pratishtha
        date(2024, 1, 26),  # Republic Day
        date(2024, 3, 8),  # Mahashivratri
        date(2024, 3, 25),  # Holi
        date(2024, 3, 29),  # Good Friday
        date(2024, 4, 11),  # Id-Ul-Fitr (Ramzan Id)
        date(2024, 4, 17),  # Shri Ram Navmi
        date(2024, 5, 1),  # Maharashtra Day
        date(2024, 5, 20),  # Special holiday - general election
        date(2024, 6, 17),  # Bakri Id
        date(2024, 7, 17),  # Muharram
        date(2024, 8, 15),  # Independence Day
        date(2024, 10, 2),  # Mahatma Gandhi Jayanti
        date(2024, 11, 1),  # Diwali Laxmi Pujan (normal session closed)
        date(2024, 11, 15),  # Gurunanak Jayanti
        date(2024, 11, 20),  # Special holiday - Maharashtra assembly election
        date(2024, 12, 25),  # Christmas
    }
)

# CONFIDENCE: high. NSE/CMTR/65587 and NSE/FAOP/65588. The circular PDFs timed out on fetch;
# the list below was reconciled across two independent public mirrors that agreed exactly.
_HOLIDAYS_2025: frozenset[date] = frozenset(
    {
        date(2025, 2, 26),  # Mahashivratri
        date(2025, 3, 14),  # Holi
        date(2025, 3, 31),  # Id-Ul-Fitr (Ramzan Id)
        date(2025, 4, 10),  # Shri Mahavir Jayanti
        date(2025, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 1),  # Maharashtra Day
        date(2025, 8, 15),  # Independence Day
        date(2025, 8, 27),  # Ganesh Chaturthi
        date(2025, 10, 2),  # Mahatma Gandhi Jayanti / Dussehra
        date(2025, 10, 21),  # Diwali Laxmi Pujan (normal session closed)
        date(2025, 10, 22),  # Diwali Balipratipada
        date(2025, 11, 5),  # Prakash Gurpurb Sri Guru Nanak Dev
        date(2025, 12, 25),  # Christmas
    }
)

# CONFIDENCE: medium-high. Reconciled across two independent public mirrors that agreed on all
# sixteen dates. One source (Groww) omitted 15-Jan-2026; treat that single date as the least
# certain entry in this module. The NSE annual circular PDF was not fetchable at build time.
_HOLIDAYS_2026: frozenset[date] = frozenset(
    {
        date(2026, 1, 15),  # Special holiday - Maharashtra municipal elections  [least certain]
        date(2026, 1, 26),  # Republic Day
        date(2026, 3, 3),  # Holi
        date(2026, 3, 26),  # Shri Ram Navmi
        date(2026, 3, 31),  # Shri Mahavir Jayanti
        date(2026, 4, 3),  # Good Friday
        date(2026, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti
        date(2026, 5, 1),  # Maharashtra Day
        date(2026, 5, 28),  # Bakri Id
        date(2026, 6, 26),  # Muharram
        date(2026, 9, 14),  # Ganesh Chaturthi
        date(2026, 10, 2),  # Mahatma Gandhi Jayanti
        date(2026, 10, 20),  # Dussehra
        date(2026, 11, 10),  # Diwali Balipratipada
        date(2026, 11, 24),  # Prakash Gurpurb Sri Guru Nanak Dev
        date(2026, 12, 25),  # Christmas
    }
)

#: Full trading-holiday set for every year this module can answer for.
NSE_HOLIDAYS: frozenset[date] = _HOLIDAYS_2024 | _HOLIDAYS_2025 | _HOLIDAYS_2026

#: Years for which a holiday list has actually been encoded. Queries outside this raise.
COVERED_YEARS: frozenset[int] = frozenset({2024, 2025, 2026})

#: Inclusive bounds of the encoded calendar. The expiry ladder is clamped to this range, so
#: ``resolve_expiry`` fails loudly near the end of coverage rather than inventing holidays.
FIRST_COVERED_DATE: date = date(min(COVERED_YEARS), 1, 1)
LAST_COVERED_DATE: date = date(max(COVERED_YEARS), 12, 31)

# Muhurat Pickup / Diwali Muhurat sessions. These are one-hour ceremonial sessions held on
# days that are otherwise trading holidays (or Sundays). They are deliberately *excluded*
# from the tradeable set: an intraday strategy calibrated on a 385-minute session cannot be
# run on a ~60-minute session.
MUHURAT_SESSIONS: frozenset[date] = frozenset(
    {
        date(2024, 11, 1),
        date(2025, 10, 21),
        date(2026, 11, 8),  # a Sunday
    }
)


def _assert_covered(d: date) -> None:
    if d.year not in COVERED_YEARS:
        raise ValueError(
            f"No NSE holiday list encoded for {d.year}; covered years are {sorted(COVERED_YEARS)}. "
            "Add the year's circular-sourced list to app/options/calendar.py before querying it."
        )


def is_weekend(d: date) -> bool:
    """Saturday or Sunday."""
    return d.weekday() >= 5


def is_holiday(d: date) -> bool:
    """True if ``d`` is an NSE trading holiday."""
    _assert_covered(d)
    return d in NSE_HOLIDAYS


def is_trading_day(d: date) -> bool:
    """True if the normal full-length session runs on ``d``.

    Muhurat sessions are *not* trading days for our purposes — see ``MUHURAT_SESSIONS``.
    """
    _assert_covered(d)
    return not is_weekend(d) and d not in NSE_HOLIDAYS


def previous_trading_day(d: date) -> date:
    """Latest trading day strictly before ``d``."""
    cursor = d - timedelta(days=1)
    for _ in range(30):
        if is_trading_day(cursor):
            return cursor
        cursor -= timedelta(days=1)
    raise ValueError(f"No trading day found in the 30 days before {d.isoformat()}")


def next_trading_day(d: date) -> date:
    """Earliest trading day strictly after ``d``."""
    cursor = d + timedelta(days=1)
    for _ in range(30):
        if is_trading_day(cursor):
            return cursor
        cursor += timedelta(days=1)
    raise ValueError(f"No trading day found in the 30 days after {d.isoformat()}")


# ── Expiry weekday regimes ───────────────────────────────────────────────────────────────

# Python weekday(): Monday=0 ... Sunday=6.
_THURSDAY = 3
_TUESDAY = 1

#: First expiry date governed by the Tuesday regime (NSE/FAOP/68747, Ref 111/2025).
EXPIRY_WEEKDAY_SWITCH_DATE: date = date(2025, 9, 1)

#: Expiry weekday before the switch.
EXPIRY_WEEKDAY_LEGACY: int = _THURSDAY

#: Expiry weekday on and after the switch.
EXPIRY_WEEKDAY_CURRENT: int = _TUESDAY

#: From this date NSE stopped issuing BANKNIFTY weekly contracts (SEBI one-weekly-per-exchange).
BANKNIFTY_WEEKLY_DISCONTINUED_FROM: date = date(2024, 11, 20)

#: Indices that still have a weekly series, and from when.
WEEKLY_SERIES: dict[Index, bool] = {
    Index.NIFTY: True,
    Index.BANKNIFTY: False,  # discontinued; see BANKNIFTY_WEEKLY_DISCONTINUED_FROM
}


def expiry_weekday(nominal_expiry: date) -> int:
    """Scheduled expiry weekday for a contract nominally expiring on ``nominal_expiry``."""
    return EXPIRY_WEEKDAY_CURRENT if nominal_expiry >= EXPIRY_WEEKDAY_SWITCH_DATE else EXPIRY_WEEKDAY_LEGACY


def _adjust_for_holiday(nominal: date) -> date:
    """Move an expiry that lands on a non-trading day back to the previous trading day.

    NSE's rule: if the expiry day is a trading holiday, the contract expires on the *previous*
    trading day.
    """
    if is_trading_day(nominal):
        return nominal
    return previous_trading_day(nominal)


def monthly_expiry(year: int, month: int) -> date:
    """Actual expiry date of the monthly index-option series for ``year``/``month``."""
    # Last day of the month.
    last = date(year, 12, 31) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)

    # Walk back to the scheduled weekday. The weekday regime is chosen from the *nominal*
    # last-weekday date, so an August-2025 monthly resolves under the Thursday rule and a
    # September-2025 monthly under the Tuesday rule.
    target_thu = last - timedelta(days=(last.weekday() - _THURSDAY) % 7)
    target_tue = last - timedelta(days=(last.weekday() - _TUESDAY) % 7)
    nominal = target_tue if target_tue >= EXPIRY_WEEKDAY_SWITCH_DATE else target_thu
    return _adjust_for_holiday(nominal)


# Generation scans a slightly wider nominal window than the requested one, because a nominal
# expiry just outside the window can be pulled *into* it by the holiday adjustment.
_LADDER_PAD_DAYS: int = 10


def _clamp(d: date) -> date:
    return min(max(d, FIRST_COVERED_DATE), LAST_COVERED_DATE)


def weekly_expiries(index: Index, start: date, end: date) -> list[date]:
    """Actual weekly expiry dates for ``index`` falling in ``[start, end]``.

    Dates returned are post-holiday-adjustment. Returns an empty list for indices whose weekly
    series has been discontinued.
    """
    if not WEEKLY_SERIES[index]:
        return []

    scan_from = _clamp(start - timedelta(days=_LADDER_PAD_DAYS))
    scan_to = _clamp(end + timedelta(days=_LADDER_PAD_DAYS))

    out: set[date] = set()
    cursor = scan_from
    while cursor <= scan_to:
        if cursor.weekday() == expiry_weekday(cursor):
            actual = _adjust_for_holiday(cursor)
            if start <= actual <= end:
                out.add(actual)
        cursor += timedelta(days=1)
    return sorted(out)


def monthly_expiries(start: date, end: date) -> list[date]:
    """Actual monthly expiry dates falling in ``[start, end]``, post-holiday-adjustment."""
    scan_from = _clamp(start - timedelta(days=_LADDER_PAD_DAYS))
    scan_to = _clamp(end + timedelta(days=_LADDER_PAD_DAYS))

    out: list[date] = []
    year, month = scan_from.year, scan_from.month
    while date(year, month, 1) <= scan_to:
        exp = monthly_expiry(year, month)
        if start <= exp <= end:
            out.append(exp)
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def expiry_ladder(index: Index, start: date, end: date) -> list[date]:
    """All tradeable expiries for ``index`` in ``[start, end]``, ascending, deduplicated.

    For NIFTY this is the union of the weekly and monthly ladders (under the current regime
    the monthly expiry *is* one of the weeklies). For BANKNIFTY it is the monthly ladder only,
    because NSE stopped issuing BANKNIFTY weeklies on ``BANKNIFTY_WEEKLY_DISCONTINUED_FROM``.
    """
    ladder = set(monthly_expiries(start, end)) | set(weekly_expiries(index, start, end))
    return sorted(ladder)


def is_monthly_expiry(expiry: date) -> bool:
    """True if ``expiry`` is the monthly series expiry for its own month."""
    return monthly_expiry(expiry.year, expiry.month) == expiry


def is_expiry_day(d: date, index: Index) -> bool:
    """True if ``d`` is an actual expiry date for ``index`` (holiday adjustment included)."""
    return d in expiry_ladder(index, d, d)


def is_expiry_day_any(d: date) -> bool:
    """True if ``d`` is an expiry date for either supported index."""
    return any(is_expiry_day(d, ix) for ix in Index)


# ── DTE resolution ───────────────────────────────────────────────────────────────────────

#: Minimum calendar days to expiry for a contract we are willing to trade.
#: Source: docs/options-paper-trading-plan.md Sec 1.3 — below 5 DTE, gamma/theta dominate and
#: the strategy's edge is swamped.
MIN_DTE: int = 5

#: How far ahead the resolver will look for a qualifying expiry before giving up. 90 days
#: comfortably covers the worst case (a BANKNIFTY monthly ladder with ~35-day gaps) without
#: running past the end of the encoded holiday data for most of the covered range.
_RESOLVE_HORIZON_DAYS: int = 90


def dte(trade_date: date, expiry: date) -> int:
    """Calendar days from ``trade_date`` to ``expiry`` (0 on expiry day)."""
    return (expiry - trade_date).days


@dataclass(frozen=True)
class ExpiryChoice:
    """The expiry the DTE>=5 rule selects on a given trade date."""

    trade_date: date
    expiry: date
    dte: int
    rolled: bool
    """True when the nearest expiry was skipped because it was inside ``MIN_DTE``."""

    is_monthly: bool


def resolve_expiry(trade_date: date, index: Index) -> ExpiryChoice:
    """Nearest expiry for ``index`` that is at least ``MIN_DTE`` calendar days out.

    Reproduces the resolution table in docs/options-paper-trading-plan.md Sec 1.3, including
    the expiry-day row (on an expiry day the nearest expiry has DTE 0, so we roll).

    Note this is *not* the same question as :func:`is_tradeable` — the resolver answers "which
    contract would we buy", the tradeability check answers "would we trade at all today".
    """
    horizon = _clamp(trade_date + timedelta(days=_RESOLVE_HORIZON_DAYS))
    ladder = expiry_ladder(index, trade_date, horizon)
    if not ladder:
        raise ValueError(f"No {index.value} expiries found within {_RESOLVE_HORIZON_DAYS} days of {trade_date}")

    nearest = ladder[0]
    for expiry in ladder:
        days = dte(trade_date, expiry)
        if days >= MIN_DTE:
            return ExpiryChoice(
                trade_date=trade_date,
                expiry=expiry,
                dte=days,
                rolled=expiry != nearest,
                is_monthly=is_monthly_expiry(expiry),
            )

    raise ValueError(
        f"No {index.value} expiry at least {MIN_DTE} days after {trade_date} within "
        f"{_RESOLVE_HORIZON_DAYS} days — extend the horizon or the holiday list"
    )


def is_tradeable(d: date, index: Index) -> bool:
    """True if we would consider opening a position in ``index`` on ``d``.

    All four conditions must hold:

    1. ``d`` is not a weekend,
    2. ``d`` is not an NSE trading holiday (Muhurat sessions count as non-trading),
    3. ``d`` is not an expiry day for ``index``,
    4. a qualifying expiry exists at least ``MIN_DTE`` calendar days out.

    Condition 3 comes from Sec 1 Scope ("Never expiry day"). Condition 4 is guaranteed by
    :func:`resolve_expiry` whenever the ladder reaches far enough ahead, and is re-checked here
    so the function fails closed at the edge of the encoded holiday data.
    """
    if not is_trading_day(d):
        return False
    if is_expiry_day(d, index):
        return False
    try:
        choice = resolve_expiry(d, index)
    except ValueError:
        return False
    return choice.dte >= MIN_DTE
