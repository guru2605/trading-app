"""Tests for app.options.calendar — trading days, session bounds, expiries, DTE resolution."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.options.calendar import (
    IST,
    MIN_DTE,
    NSE_HOLIDAYS,
    SESSION_CLOSE,
    SESSION_CLOSE_EXTENSION_DATE,
    SESSION_CLOSE_LEGACY,
    SESSION_MINUTES,
    SESSION_MINUTES_LEGACY,
    SESSION_OPEN,
    WINDOW_CLOSE,
    WINDOW_OPEN,
    dte,
    entry_window_bounds,
    expiry_ladder,
    is_expiry_day,
    is_holiday,
    is_monthly_expiry,
    is_tradeable,
    is_trading_day,
    is_weekend,
    monthly_expiry,
    next_trading_day,
    previous_trading_day,
    resolve_expiry,
    session_bounds,
    session_close_time,
    session_minutes,
    to_ist,
    weekly_expiries,
)
from app.options.contracts import Index

# ── Session bounds ───────────────────────────────────────────────────────────────────────


def test_session_is_385_minutes_under_the_current_timings() -> None:
    # 09:15 to 15:40 IST. 375 was the Rev 1 error documented in Sec 8 of the plan.
    assert SESSION_OPEN.isoformat() == time(9, 15).isoformat()
    assert SESSION_CLOSE.isoformat() == time(15, 40).isoformat()
    assert SESSION_MINUTES == 385


def test_session_minutes_matches_the_bounds_it_claims() -> None:
    for on in (date(2026, 8, 28), date(2025, 6, 10)):
        start, end = session_bounds(on)
        assert (end - start).total_seconds() / 60 == session_minutes(on)


def test_session_close_extension_is_date_keyed() -> None:
    day_before = date(2026, 7, 31)  # Friday before the 03-Aug-2026 extension
    assert session_close_time(day_before) == SESSION_CLOSE_LEGACY
    assert session_minutes(day_before) == SESSION_MINUTES_LEGACY
    assert session_close_time(SESSION_CLOSE_EXTENSION_DATE) == SESSION_CLOSE
    assert session_minutes(SESSION_CLOSE_EXTENSION_DATE) == SESSION_MINUTES


def test_entry_window_is_the_first_45_minutes() -> None:
    assert WINDOW_OPEN.isoformat() == time(9, 15).isoformat()
    assert WINDOW_CLOSE.isoformat() == time(10, 0).isoformat()
    start, end = entry_window_bounds(date(2026, 8, 28))
    assert (end - start).total_seconds() / 60 == 45


def test_all_datetimes_are_ist_aware() -> None:
    start, end = session_bounds(date(2026, 8, 28))
    for moment in (start, end, *entry_window_bounds(date(2026, 8, 28))):
        assert moment.tzinfo is not None
        assert moment.utcoffset() is not None
        assert moment.tzinfo is IST


def test_to_ist_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="Naive datetime"):
        to_ist(datetime(2026, 8, 28, 9, 15))  # deliberately naive


def test_to_ist_converts_from_utc() -> None:
    utc_moment = datetime(2026, 8, 28, 3, 45, tzinfo=UTC)
    converted = to_ist(utc_moment)
    assert converted.hour == 9
    assert converted.minute == 15
    assert converted.tzinfo == ZoneInfo("Asia/Kolkata")


# ── Trading days ─────────────────────────────────────────────────────────────────────────


def test_weekends_are_not_trading_days() -> None:
    saturday = date(2026, 8, 29)
    sunday = date(2026, 8, 30)
    assert is_weekend(saturday) and is_weekend(sunday)
    assert not is_trading_day(saturday)
    assert not is_trading_day(sunday)


@pytest.mark.parametrize(
    "holiday",
    [
        date(2024, 1, 22),  # Ram Mandir special holiday
        date(2024, 5, 20),  # general election special holiday
        date(2025, 8, 15),  # Independence Day
        date(2025, 10, 21),  # Diwali Laxmi Pujan (Muhurat session only)
        date(2026, 1, 26),  # Republic Day
        date(2026, 12, 25),  # Christmas
    ],
)
def test_known_holidays(holiday: date) -> None:
    assert is_holiday(holiday)
    assert not is_trading_day(holiday)


def test_a_muhurat_day_is_not_a_normal_trading_day() -> None:
    # A ~60-minute ceremonial session cannot host a strategy calibrated on 385 minutes.
    assert not is_trading_day(date(2025, 10, 21))


def test_ordinary_weekday_is_a_trading_day() -> None:
    assert is_trading_day(date(2026, 8, 28))  # Friday, not a holiday


def test_queries_outside_the_encoded_years_fail_loudly() -> None:
    with pytest.raises(ValueError, match="No NSE holiday list encoded"):
        is_trading_day(date(2027, 1, 4))
    with pytest.raises(ValueError, match="No NSE holiday list encoded"):
        is_holiday(date(2023, 1, 4))


def test_holiday_lists_contain_no_weekend_dates() -> None:
    # A weekend entry would be harmless but signals a transcription error in the circular list.
    weekend_holidays = sorted(d for d in NSE_HOLIDAYS if is_weekend(d))
    assert weekend_holidays == []


def test_previous_and_next_trading_day_skip_the_long_weekend() -> None:
    # 2026-01-26 (Republic Day) is a Monday, so Fri 23rd -> Tue 27th.
    assert date(2026, 1, 26).weekday() == 0
    assert next_trading_day(date(2026, 1, 23)) == date(2026, 1, 27)
    assert previous_trading_day(date(2026, 1, 27)) == date(2026, 1, 23)


# ── Expiries ─────────────────────────────────────────────────────────────────────────────


def test_expiry_moved_from_thursday_to_tuesday_in_september_2025() -> None:
    # NSE/FAOP/68747 (Ref 111/2025): contracts expiring on/after 01-Sep-2025 move to Tuesday.
    august = monthly_expiry(2025, 8)
    september = monthly_expiry(2025, 9)
    assert august.weekday() == 3, f"Aug-2025 monthly should be a Thursday, got {august}"
    assert september.weekday() == 1, f"Sep-2025 monthly should be a Tuesday, got {september}"


def test_monthly_expiry_is_the_last_tuesday_under_the_current_regime() -> None:
    expiry = monthly_expiry(2026, 8)
    assert expiry.weekday() == 1
    # No later Tuesday in the month.
    assert (expiry.day + 7) > 31 or date(2026, 8, expiry.day + 7).month != 8


def test_monthly_expiry_moves_back_when_it_lands_on_a_holiday() -> None:
    # 2026-03-31 (Shri Mahavir Jayanti) is a Tuesday and would be the March-2026 monthly
    # expiry; NSE moves an expiry that lands on a holiday to the previous trading day.
    assert date(2026, 3, 31).weekday() == 1
    assert is_holiday(date(2026, 3, 31))
    expiry = monthly_expiry(2026, 3)
    assert expiry == date(2026, 3, 30)
    assert is_trading_day(expiry)


def test_holiday_adjusted_expiry_is_reported_as_an_expiry_day() -> None:
    # Regression: the ladder used to filter on the *nominal* date, so the pulled-back expiry
    # was invisible to is_expiry_day().
    assert is_expiry_day(date(2026, 3, 30), Index.NIFTY)
    assert not is_expiry_day(date(2026, 3, 31), Index.NIFTY)


def test_banknifty_has_no_weekly_series() -> None:
    # SEBI/HO/MRD/MRD-PoD-3/P/CIR/2024/132: one weekly benchmark per exchange; NSE kept NIFTY.
    assert weekly_expiries(Index.BANKNIFTY, date(2026, 6, 1), date(2026, 6, 30)) == []
    banknifty = expiry_ladder(Index.BANKNIFTY, date(2026, 6, 1), date(2026, 6, 30))
    assert banknifty == [monthly_expiry(2026, 6)]


def test_nifty_ladder_is_weekly() -> None:
    ladder = expiry_ladder(Index.NIFTY, date(2026, 6, 1), date(2026, 6, 30))
    assert len(ladder) >= 4
    assert all(d.weekday() == 1 for d in ladder), ladder
    assert ladder == sorted(set(ladder))


def test_is_monthly_expiry() -> None:
    june_monthly = monthly_expiry(2026, 6)
    assert is_monthly_expiry(june_monthly)
    nifty_weeklies = [d for d in expiry_ladder(Index.NIFTY, date(2026, 6, 1), date(2026, 6, 30)) if d != june_monthly]
    assert nifty_weeklies
    assert not any(is_monthly_expiry(d) for d in nifty_weeklies)


# ── DTE resolution — the Sec 1.3 acceptance gate ─────────────────────────────────────────

# docs/options-paper-trading-plan.md Sec 1.3 tabulates the DTE>=5 rule against a
# holiday-free week with Tuesday expiries. The week of 01-Jun-2026 is exactly such a week
# (Tuesday expiries 02, 09 and 16 June 2026; no NSE holiday falls in it).
#
#   Trade day  Next Tue  DTE  Action  Final DTE
#   Mon        +1        1    roll    8
#   Tue        0         0    roll    7
#   Wed        +6        6    take    6
#   Thu        +5        5    take    5
#   Fri        +4        4    roll    11
SEC_1_3_TABLE: list[tuple[date, int, bool, int]] = [
    # (trade date, nearest-expiry DTE, expected to roll, final DTE)
    (date(2026, 6, 1), 1, True, 8),
    (date(2026, 6, 2), 0, True, 7),
    (date(2026, 6, 3), 6, False, 6),
    (date(2026, 6, 4), 5, False, 5),
    (date(2026, 6, 5), 4, True, 11),
]


def test_sec_1_3_week_is_the_holiday_free_tuesday_week_the_table_assumes() -> None:
    for offset, weekday in enumerate(range(5)):  # Mon..Fri
        day = date(2026, 6, 1 + offset)
        assert day.weekday() == weekday
        assert is_trading_day(day), f"{day} must be a trading day for the Sec 1.3 table to hold"
    for expiry in (date(2026, 6, 2), date(2026, 6, 9), date(2026, 6, 16)):
        assert expiry.weekday() == 1
        assert is_expiry_day(expiry, Index.NIFTY)


@pytest.mark.parametrize(("trade_date", "nearest_dte", "rolled", "final_dte"), SEC_1_3_TABLE)
def test_resolver_reproduces_sec_1_3_table(trade_date: date, nearest_dte: int, rolled: bool, final_dte: int) -> None:
    ladder = expiry_ladder(Index.NIFTY, trade_date, date(2026, 7, 31))
    assert dte(trade_date, ladder[0]) == nearest_dte

    choice = resolve_expiry(trade_date, Index.NIFTY)
    assert choice.dte == final_dte
    assert choice.rolled is rolled
    assert choice.dte >= MIN_DTE
    assert choice.trade_date == trade_date


def test_dte_is_zero_on_expiry_day() -> None:
    assert dte(date(2026, 6, 9), date(2026, 6, 9)) == 0
    assert dte(date(2026, 6, 4), date(2026, 6, 9)) == 5


# ── Tradeability ─────────────────────────────────────────────────────────────────────────


def test_not_tradeable_on_weekends_or_holidays() -> None:
    assert not is_tradeable(date(2026, 8, 29), Index.NIFTY)  # Saturday
    assert not is_tradeable(date(2026, 1, 26), Index.NIFTY)  # Republic Day


def test_not_tradeable_on_an_expiry_day() -> None:
    # Sec 1 Scope: "Never expiry day". Note the Sec 1.3 resolver table still *has* a row for
    # trading on a Tuesday expiry (it rolls to DTE 7) — the two rules are separate, and the
    # tradeability gate is the stricter one. Flagged as a doc ambiguity.
    expiry = date(2026, 6, 9)
    assert is_expiry_day(expiry, Index.NIFTY)
    assert is_trading_day(expiry)
    assert resolve_expiry(expiry, Index.NIFTY).dte == 7
    assert not is_tradeable(expiry, Index.NIFTY)


def test_tradeable_on_an_ordinary_midweek_day() -> None:
    assert is_tradeable(date(2026, 6, 3), Index.NIFTY)
    assert is_tradeable(date(2026, 6, 4), Index.NIFTY)


def test_tradeable_days_always_have_a_qualifying_expiry() -> None:
    day = date(2026, 6, 1)
    checked = 0
    while day <= date(2026, 6, 30):
        if is_tradeable(day, Index.NIFTY):
            assert resolve_expiry(day, Index.NIFTY).dte >= MIN_DTE
            checked += 1
        day += timedelta(days=1)
    assert checked > 10
