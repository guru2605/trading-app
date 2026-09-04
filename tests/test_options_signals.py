"""Tests for the Phase 2 index-level signal test — app.options.signals + signal_test.

Pure-logic only: signal triggering, the no-lookahead entry rule, the exact binomial tail,
deflation, and the held-out split. No test touches the network; the one Kite-shaped payload
exercised goes through :func:`app.options.histdata.parse_candles` as a literal.
"""

import sqlite3
from datetime import date, datetime, time, timedelta

import pytest

from app.options.calendar import IST
from app.options.histdata import (
    MAX_DAYS_PER_REQUEST,
    Bar,
    chunk_ranges,
    ensure_schema,
    find_index_token,
    load_days,
    missing_chunks,
    parse_candles,
    store_candles,
)
from app.options.signals import (
    CONFIGS,
    GAP_CONTINUATION_THRESHOLD,
    GAP_FADE_THRESHOLD,
    LAST_ENTRY,
    LONG,
    MOMENTUM_THRESHOLD,
    SHORT,
    extract_signals,
    gap_return,
    momentum_return,
    opening_range,
    signals_for_day,
)
from app.options.signal_test import (
    ALPHA,
    NUM_HYPOTHESES,
    binomial_p_at_least,
    bonferroni,
    fold_bounds,
    holdout_start,
    sidak,
    summarise,
)

DAY = date(2026, 6, 3)


def _bars(day: date, closes: dict[time, float], *, base: float = 25000.0, until: time = time(10, 0)) -> list[Bar]:
    """A synthetic session: flat at ``base`` except where ``closes`` overrides a minute.

    Each bar's open is the previous bar's close, so the series is continuous and the
    no-lookahead entry price (next bar's open) is well defined.
    """
    bars: list[Bar] = []
    previous = base
    minute = datetime.combine(day, time(9, 15), tzinfo=IST)
    end = datetime.combine(day, until, tzinfo=IST)
    while minute < end:
        close = closes.get(minute.time(), previous)
        bars.append(Bar(minute, previous, max(previous, close), min(previous, close), close))
        previous = close
        minute += timedelta(minutes=1)
    return bars


# ── Opening range and the ORB trigger ────────────────────────────────────────────────────


def test_opening_range_covers_0915_to_0929_inclusive() -> None:
    bars = _bars(DAY, {time(9, 20): 25100.0, time(9, 30): 25400.0})
    high, low = opening_range(bars)
    assert high == 25100.0  # the 09:30 spike is outside the range window
    assert low == 25000.0


def test_orb_triggers_on_the_first_close_outside_the_range() -> None:
    bars = _bars(DAY, {time(9, 20): 25100.0, time(9, 35): 25150.0, time(9, 59): 25300.0})
    (signal,) = [s for s in signals_for_day(bars, None) if s.config == "orb"]
    assert signal.direction == LONG
    assert signal.entry_ts.time() == time(9, 36)  # entry is the bar AFTER the trigger
    assert signal.entry == 25150.0  # ... at its open, which is the trigger bar's close
    assert signal.exit_ts.time() == time(10, 0)
    assert signal.exit == 25300.0
    assert signal.hit is True


def test_orb_short_break_is_a_hit_when_the_index_falls() -> None:
    bars = _bars(DAY, {time(9, 20): 25100.0, time(9, 35): 24900.0, time(9, 59): 24800.0})
    (signal,) = [s for s in signals_for_day(bars, None) if s.config == "orb"]
    assert signal.direction == SHORT
    assert signal.signed_return > 0 and signal.hit is True


def test_orb_short_break_that_reverses_is_a_miss() -> None:
    bars = _bars(DAY, {time(9, 20): 25100.0, time(9, 35): 24900.0, time(9, 59): 25500.0})
    (signal,) = [s for s in signals_for_day(bars, None) if s.config == "orb"]
    assert signal.direction == SHORT
    assert signal.hit is False


def test_orb_does_not_trigger_on_a_close_exactly_on_the_boundary() -> None:
    # The range must be exceeded, not touched: a boundary close is not a break.
    bars = _bars(DAY, {time(9, 20): 25100.0, time(9, 35): 25100.0})
    assert [s for s in signals_for_day(bars, None) if s.config == "orb"] == []


def test_orb_is_skipped_when_the_break_leaves_no_horizon() -> None:
    # A break whose entry lands after LAST_ENTRY is a coin flip, not a trade.
    late = time(LAST_ENTRY.hour, LAST_ENTRY.minute + 1)
    bars = _bars(DAY, {time(9, 20): 25100.0, late: 25400.0})
    assert [s for s in signals_for_day(bars, None) if s.config == "orb"] == []


def test_orb_never_reads_a_bar_at_or_after_its_own_entry() -> None:
    # Lookahead assertion: the entry price must exist in the bar series strictly after the
    # trigger, and the exit must be strictly after the entry.
    bars = _bars(DAY, {time(9, 20): 25100.0, time(9, 40): 25200.0, time(9, 59): 25000.0})
    (signal,) = [s for s in signals_for_day(bars, None) if s.config == "orb"]
    assert signal.entry_ts.time() == time(9, 41)  # break at 09:40, entry the minute after
    assert signal.entry_ts < signal.exit_ts
    assert signal.horizon_minutes == pytest.approx(19.0)  # 09:41 -> 10:00


# ── Gap configs ──────────────────────────────────────────────────────────────────────────


def test_gap_return_is_measured_against_the_previous_close() -> None:
    bars = _bars(DAY, {}, base=25250.0)
    assert gap_return(bars, 25000.0) == pytest.approx(0.01)


def test_gap_continuation_trades_with_the_gap_and_enters_at_0920() -> None:
    previous_close = 25000.0
    open_price = previous_close * (1 + GAP_CONTINUATION_THRESHOLD * 2)
    bars = _bars(DAY, {time(9, 59): open_price * 1.01}, base=open_price)
    (signal,) = [s for s in signals_for_day(bars, previous_close) if s.config == "gap_cont"]
    assert signal.direction == LONG
    assert signal.entry_ts.time() == time(9, 20)
    assert signal.hit is True


def test_gap_fade_trades_against_the_gap() -> None:
    previous_close = 25000.0
    open_price = previous_close * (1 + GAP_FADE_THRESHOLD * 2)
    bars = _bars(DAY, {}, base=open_price)
    (signal,) = [s for s in signals_for_day(bars, previous_close) if s.config == "gap_fade"]
    assert signal.direction == SHORT


def test_a_gap_below_the_threshold_triggers_nothing() -> None:
    previous_close = 25000.0
    bars = _bars(DAY, {}, base=previous_close * 1.001)  # 0.1%, under both thresholds
    configs = {s.config for s in signals_for_day(bars, previous_close)}
    assert "gap_cont" not in configs and "gap_fade" not in configs


def test_a_gap_between_the_two_thresholds_fires_continuation_only() -> None:
    previous_close = 25000.0
    bars = _bars(DAY, {}, base=previous_close * 1.004)  # > 0.3%, < 0.5%
    configs = {s.config for s in signals_for_day(bars, previous_close)}
    assert "gap_cont" in configs and "gap_fade" not in configs


def test_the_first_session_has_no_previous_close_and_so_no_gap_signals() -> None:
    bars = _bars(DAY, {time(9, 20): 25100.0, time(9, 35): 25200.0})
    configs = {s.config for s in signals_for_day(bars, None)}
    assert configs <= {"orb", "mom"}


# ── Momentum config ──────────────────────────────────────────────────────────────────────


def test_momentum_return_runs_from_the_0915_open_to_the_0924_close() -> None:
    bars = _bars(DAY, {time(9, 24): 25050.0, time(9, 30): 25900.0})
    assert momentum_return(bars) == pytest.approx(0.002)


def test_momentum_triggers_above_the_threshold_and_enters_at_0925() -> None:
    move = 1 + MOMENTUM_THRESHOLD * 2
    bars = _bars(DAY, {time(9, 24): 25000.0 * move, time(9, 59): 25000.0 * move * 1.01})
    (signal,) = [s for s in signals_for_day(bars, None) if s.config == "mom"]
    assert signal.direction == LONG
    assert signal.entry_ts.time() == time(9, 25)
    assert signal.hit is True


def test_momentum_just_below_the_threshold_does_not_trigger() -> None:
    # The comparison is `<=`, so the threshold itself is not a trigger. An exactly-on-the-line
    # move is unrepresentable in binary floats, so the boundary is probed from just below.
    bars = _bars(DAY, {time(9, 24): 25000.0 * (1 + MOMENTUM_THRESHOLD * 0.99)})
    assert [s for s in signals_for_day(bars, None) if s.config == "mom"] == []


# ── Session handling ─────────────────────────────────────────────────────────────────────


def test_a_flat_session_triggers_nothing() -> None:
    assert signals_for_day(_bars(DAY, {}), 25000.0) == []


def test_a_session_with_no_bars_before_1000_is_skipped() -> None:
    late_only = [Bar(datetime.combine(DAY, time(10, 30), tzinfo=IST), 1.0, 1.0, 1.0, 1.0)]
    assert signals_for_day(late_only, 25000.0) == []


def test_extract_signals_carries_the_previous_close_across_sessions() -> None:
    first = _bars(DAY, {}, base=25000.0)
    # Second session opens 1% up on the first session's close -> both gap configs fire.
    second = _bars(date(2026, 6, 4), {}, base=25250.0)
    configs = {s.config for s in extract_signals([first, second])}
    assert {"gap_cont", "gap_fade"} <= configs


def test_four_hypotheses_cover_all_six_registered_configs() -> None:
    registered = {name for names in CONFIGS.values() for name in names}
    assert registered == {"orb_synth", "orb_naked", "gap_cont_synth", "gap_fade_synth", "mom_synth", "mom_naked"}
    assert NUM_HYPOTHESES == 4


# ── Statistics ───────────────────────────────────────────────────────────────────────────


def test_binomial_tail_is_exact_on_hand_checkable_cases() -> None:
    assert binomial_p_at_least(0, 10) == 1.0
    assert binomial_p_at_least(10, 10) == pytest.approx(1 / 1024)
    assert binomial_p_at_least(9, 10) == pytest.approx(11 / 1024)
    assert binomial_p_at_least(5, 10) == pytest.approx(638 / 1024)


def test_binomial_tail_of_an_empty_sample_is_not_significant() -> None:
    assert binomial_p_at_least(0, 0) == 1.0


def test_a_coin_flip_is_never_significant_however_many_sessions() -> None:
    assert binomial_p_at_least(500, 1000) > ALPHA


def test_deflation_makes_a_marginal_result_insignificant() -> None:
    marginal = 0.03  # would pass alone
    assert marginal < ALPHA
    assert bonferroni(marginal) > ALPHA
    assert bonferroni(marginal) >= sidak(marginal)  # Bonferroni is the conservative one


def test_deflation_is_capped_at_one() -> None:
    assert bonferroni(0.9) == 1.0


def _signal(day: date, direction: int, entry: float, exit_: float, config: str = "orb"):  # type: ignore[no-untyped-def]
    from app.options.signals import Signal

    return Signal(
        day=day,
        config=config,
        direction=direction,
        entry_ts=datetime.combine(day, time(9, 32), tzinfo=IST),
        entry=entry,
        exit_ts=datetime.combine(day, time(10, 0), tzinfo=IST),
        exit=exit_,
    )


def test_summarise_counts_hits_and_signs_returns() -> None:
    signals = [
        _signal(date(2026, 6, 1), LONG, 25000.0, 25100.0),  # hit
        _signal(date(2026, 6, 2), LONG, 25000.0, 24900.0),  # miss
        _signal(date(2026, 6, 3), SHORT, 25000.0, 24900.0),  # hit
    ]
    result = summarise("orb", "orb", signals, sessions=10)
    assert result.n == 3 and result.hits == 2
    assert result.hit_rate == pytest.approx(2 / 3)
    assert result.trigger_rate == pytest.approx(0.3)
    assert result.mean_return == pytest.approx((0.004 - 0.004 + 0.004) / 3)


def test_summarise_ignores_other_configs() -> None:
    signals = [_signal(DAY, LONG, 25000.0, 25100.0, config="mom")]
    assert summarise("orb", "orb", signals, sessions=1).n == 0


def test_a_below_even_hit_rate_is_eliminated_however_large_the_sample() -> None:
    losers = [_signal(date(2026, 6, 1) + timedelta(days=i), LONG, 25000.0, 24900.0) for i in range(200)]
    assert summarise("orb", "orb", losers, sessions=200).survives is False


def test_a_strong_result_survives_even_after_deflation() -> None:
    # 80 of 100 correct is far outside anything four coins produce; the gate must let it past,
    # or the test could never report a survivor at all.
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(100)]
    signals = [_signal(d, LONG, 25000.0, 25100.0) for d in days[:80]]
    signals += [_signal(d, LONG, 25000.0, 24900.0) for d in days[80:]]
    result = summarise("orb", "orb", signals, sessions=100)
    assert result.p_deflated < ALPHA and result.survives is True


# ── Splitting ────────────────────────────────────────────────────────────────────────────


def test_holdout_is_six_months_back_and_survives_year_and_month_ends() -> None:
    assert holdout_start(date(2026, 9, 4)) == date(2026, 3, 4)
    assert holdout_start(date(2026, 2, 27)) == date(2025, 8, 27)
    assert holdout_start(date(2026, 1, 31)) == date(2025, 7, 28)  # clamped off the 31st


def test_fold_bounds_are_sequential_and_cover_everything() -> None:
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(100)]
    bounds = fold_bounds(days, folds=4)
    assert len(bounds) == 4
    assert bounds[0][0] == days[0] and bounds[-1][1] == days[-1]
    for (_, earlier_end), (later_start, _) in zip(bounds, bounds[1:]):
        assert earlier_end < later_start


def test_fold_bounds_of_an_empty_history_is_empty() -> None:
    assert fold_bounds([], folds=4) == []


# ── Candle cache ─────────────────────────────────────────────────────────────────────────


def test_parse_candles_reads_kites_array_shape() -> None:
    payload = {"data": {"candles": [["2026-06-03T09:15:00+0530", 25000.1, 25010.0, 24995.0, 25005.0, 0]]}}
    (bar,) = parse_candles(payload)
    assert bar.ts == datetime(2026, 6, 3, 9, 15, tzinfo=IST)
    assert (bar.open, bar.high, bar.low, bar.close) == (25000.1, 25010.0, 24995.0, 25005.0)


def test_chunk_ranges_respect_kites_sixty_day_cap() -> None:
    chunks = chunk_ranges(date(2026, 1, 1), date(2026, 6, 30))
    assert all((hi - lo).days < MAX_DAYS_PER_REQUEST for lo, hi in chunks)
    assert chunks[0][0] == date(2026, 1, 1) and chunks[-1][1] == date(2026, 6, 30)
    for (_, earlier_end), (later_start, _) in zip(chunks, chunks[1:]):
        assert later_start == earlier_end + timedelta(days=1)  # no gap, no overlap


def test_chunk_ranges_of_a_backwards_span_is_empty() -> None:
    assert chunk_ranges(date(2026, 6, 30), date(2026, 1, 1)) == []


def test_missing_chunks_skips_what_was_already_fetched() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    first = chunk_ranges(date(2026, 1, 1), date(2026, 6, 30))[0]
    conn.execute(
        "INSERT INTO fetch_chunks (from_date, to_date, candles, fetched_at) VALUES (?, ?, 0, '')",
        (first[0].isoformat(), first[1].isoformat()),
    )
    pending = missing_chunks(conn, date(2026, 1, 1), date(2026, 6, 30))
    assert first not in pending
    # A holiday-only chunk stores zero candles and must still count as fetched, or it would
    # be pulled again on every run forever.
    assert len(pending) == len(chunk_ranges(date(2026, 1, 1), date(2026, 6, 30))) - 1


def test_load_days_groups_bars_into_sessions_in_order() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    store_candles(conn, _bars(date(2026, 6, 3), {}) + _bars(date(2026, 6, 4), {}, base=25100.0))
    sessions = list(load_days(conn))
    assert len(sessions) == 2
    assert [session[0].ts.date() for session in sessions] == [date(2026, 6, 3), date(2026, 6, 4)]
    assert all(session == sorted(session, key=lambda bar: bar.ts) for session in sessions)


def test_find_index_token_ignores_equities_of_the_same_name() -> None:
    dump = [
        {"instrument_token": "999", "tradingsymbol": "NIFTY 50", "segment": "NSE"},
        {"instrument_token": "256265", "tradingsymbol": "NIFTY 50", "segment": "INDICES"},
    ]
    assert find_index_token(dump) == 256265


def test_find_index_token_fails_loudly_when_the_dump_changes_shape() -> None:
    with pytest.raises(LookupError):
        find_index_token([{"instrument_token": "1", "tradingsymbol": "SENSEX", "segment": "INDICES"}])
