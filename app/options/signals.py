"""Index-level directional signals for the Phase 2 hit-rate test — pure, no I/O.

Plan doc § Phase 2 (revised): the expired-options backtest is withdrawn, and its statistical
role passes to a hit-rate test on the NIFTY index itself — *does a 09:15–09:30 range break
predict direction over the next 28 minutes?* This module is the "does it trigger, and which
way" half of that question, expressed on index minute candles alone.

**Six configs, four signals.** §3.5 pre-registers six configs, but `orb_naked` differs from
`orb_synth`, and `mom_naked` from `mom_synth`, only in the *option structure* used to express
the view. The underlying directional claim is identical, so at index level there are four
distinct hypotheses, not six — and four is therefore the multiple-comparisons count the test
deflates by (see signal_test.py). Claiming six tests where four were run would inflate the
correction; claiming two would understate it.

**No lookahead, by construction.** A signal is *observed* at the close of some bar and
*entered* at the open of the next one. Never at the bar that produced the signal — an index
close is not tradeable at the instant it prints, and the whole point of the exercise is to
avoid the free money that a lookahead grants. :func:`extract_signals` is the only entry point
and every rule below routes through the same ``entry = open of the first bar strictly after
observation`` convention.

Exit is the same for all four: the close of the 09:59 bar, i.e. the 10:00 index level, which
is the hard time stop of §3.6 item 3. This module deliberately models **no stop and no
target** — it measures whether direction is predicted at all. Stops, targets, spreads, costs
and the option greeks are Phase 3's question, asked only of a signal that survives here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.options.histdata import Bar

# ── Timing ───────────────────────────────────────────────────────────────────────────────

SESSION_OPEN: time = time(9, 15)

#: End of the opening range, exclusive: bars 09:15..09:29 inclusive form the 09:15–09:30
#: range of §3.5 config #1.
RANGE_END: time = time(9, 30)

#: Earliest entry permitted by §3.5 ("entry no earlier than 09:20"), and the pre-registered
#: entry minute for both gap configs (#3, #4).
GAP_ENTRY: time = time(9, 20)

#: End of the "first 10-min return" of §3.5 config #5, exclusive: bars 09:15..09:24. The
#: return is measured to the close of the 09:24 bar and entered at the 09:25 open.
MOMENTUM_END: time = time(9, 25)

#: Hard time stop, §3.6 item 3. The exit price is the close of the last bar strictly before
#: it — the 09:59 bar on a complete session.
WINDOW_CLOSE: time = time(10, 0)

#: An ORB break arriving after this leaves too little residual horizon to be a trade rather
#: than a coin flip; those days are recorded as no-trade, and the skip count is reported.
#: §3.6's loophole #18 is precisely that the residual window, not a constant, governs.
LAST_ENTRY: time = time(9, 55)


# ── Thresholds, pre-registered in §3.5 ───────────────────────────────────────────────────

GAP_CONTINUATION_THRESHOLD = 0.003  # |gap| > 0.3%, trade with the gap
GAP_FADE_THRESHOLD = 0.005  # |gap| > 0.5%, trade against the gap
MOMENTUM_THRESHOLD = 0.002  # |first 10-min return| > 0.2%

#: The four distinct index-level hypotheses, and the §3.5 configs each one stands for.
CONFIGS: dict[str, tuple[str, ...]] = {
    "orb": ("orb_synth", "orb_naked"),
    "gap_cont": ("gap_cont_synth",),
    "gap_fade": ("gap_fade_synth",),
    "mom": ("mom_synth", "mom_naked"),
}

LONG = 1
SHORT = -1


@dataclass(frozen=True)
class Signal:
    """One triggered signal and the index move that followed it."""

    day: date
    config: str
    direction: int  # +1 long, -1 short
    entry_ts: datetime
    entry: float
    exit_ts: datetime
    exit: float

    @property
    def raw_return(self) -> float:
        """Index return from entry to the 10:00 stop, unsigned."""
        return self.exit / self.entry - 1.0

    @property
    def signed_return(self) -> float:
        """Return in the direction traded. Negative means the signal pointed the wrong way."""
        return self.direction * self.raw_return

    @property
    def hit(self) -> bool:
        """Did the index move the way the signal said?

        A dead-flat close counts as a miss, not a push. It is vanishingly rare on a 5-digit
        index, and rounding an ambiguous outcome towards the hypothesis is how hit rates get
        flattered.
        """
        return self.signed_return > 0

    @property
    def horizon_minutes(self) -> float:
        return (self.exit_ts - self.entry_ts).total_seconds() / 60.0


# ── Bar helpers ──────────────────────────────────────────────────────────────────────────


def _at(bars: Sequence[Bar], moment: time) -> Bar | None:
    """The bar starting exactly at ``moment``, or None if the session has no such bar."""
    for bar in bars:
        if bar.ts.time() == moment:
            return bar
    return None


def _between(bars: Sequence[Bar], start: time, end: time) -> list[Bar]:
    """Bars with start time in [start, end)."""
    return [bar for bar in bars if start <= bar.ts.time() < end]


def exit_bar(bars: Sequence[Bar]) -> Bar | None:
    """The last bar strictly before 10:00 — its close is the hard-time-stop price."""
    before = [bar for bar in bars if bar.ts.time() < WINDOW_CLOSE]
    return before[-1] if before else None


def _entry_after(bars: Sequence[Bar], observed_at: datetime) -> Bar | None:
    """The first bar starting strictly after ``observed_at``. This is the no-lookahead rule."""
    for bar in bars:
        if bar.ts > observed_at:
            return bar
    return None


def _make(day: date, config: str, direction: int, entry: Bar, exit_: Bar) -> Signal | None:
    if entry.ts.time() > LAST_ENTRY or entry.ts >= exit_.ts:
        return None
    return Signal(
        day=day,
        config=config,
        direction=direction,
        entry_ts=entry.ts,
        entry=entry.open,
        exit_ts=exit_.ts + timedelta(minutes=1),  # the 09:59 bar's close is the 10:00 level
        exit=exit_.close,
    )


# ── The four signals ─────────────────────────────────────────────────────────────────────


def opening_range(bars: Sequence[Bar]) -> tuple[float, float] | None:
    """High and low of 09:15–09:30, or None if those bars are missing."""
    window = _between(bars, SESSION_OPEN, RANGE_END)
    if not window:
        return None
    return max(bar.high for bar in window), min(bar.low for bar in window)


def gap_return(bars: Sequence[Bar], previous_close: float) -> float | None:
    """Overnight gap as a fraction of the previous session's close."""
    first = _at(bars, SESSION_OPEN)
    if first is None or previous_close <= 0:
        return None
    return first.open / previous_close - 1.0


def momentum_return(bars: Sequence[Bar]) -> float | None:
    """§3.5 #5: the first 10-min return, 09:15 open to the close of the 09:24 bar."""
    window = _between(bars, SESSION_OPEN, MOMENTUM_END)
    if not window or window[0].ts.time() != SESSION_OPEN:
        return None
    return window[-1].close / window[0].open - 1.0


def orb(bars: Sequence[Bar], exit_: Bar) -> Signal | None:
    """§3.5 #1/#2: first close outside the 09:15–09:30 range, traded in the break direction.

    Scanned from 09:30 onward; the *close* of a bar outside the range is the trigger and the
    next bar's open is the entry. Ties (a close exactly on the boundary) are not breaks — the
    range must be exceeded, not touched.
    """
    bounds = opening_range(bars)
    if bounds is None:
        return None
    high, low = bounds
    for bar in bars:
        if bar.ts.time() < RANGE_END:
            continue
        if bar.ts >= exit_.ts:
            return None  # no break inside the window
        direction = LONG if bar.close > high else SHORT if bar.close < low else 0
        if direction == 0:
            continue
        entry = _entry_after(bars, bar.ts)
        if entry is None:
            return None
        return _make(bar.ts.date(), "orb", direction, entry, exit_)
    return None


def gap_continuation(bars: Sequence[Bar], previous_close: float, exit_: Bar) -> Signal | None:
    """§3.5 #3: gap beyond ±0.3%, entered 09:20, traded *with* the gap."""
    gap = gap_return(bars, previous_close)
    if gap is None or abs(gap) <= GAP_CONTINUATION_THRESHOLD:
        return None
    entry = _at(bars, GAP_ENTRY)
    if entry is None:
        return None
    return _make(entry.ts.date(), "gap_cont", LONG if gap > 0 else SHORT, entry, exit_)


def gap_fade(bars: Sequence[Bar], previous_close: float, exit_: Bar) -> Signal | None:
    """§3.5 #4: gap beyond ±0.5%, traded *against* the gap.

    §3.5 gives no entry minute for this config; it inherits #3's 09:20, which is also the
    earliest the section permits. Fixing it rather than searching for a better one is the
    point — a scanned entry time would be a fifth hypothesis to deflate for.
    """
    gap = gap_return(bars, previous_close)
    if gap is None or abs(gap) <= GAP_FADE_THRESHOLD:
        return None
    entry = _at(bars, GAP_ENTRY)
    if entry is None:
        return None
    return _make(entry.ts.date(), "gap_fade", SHORT if gap > 0 else LONG, entry, exit_)


def momentum(bars: Sequence[Bar], exit_: Bar) -> Signal | None:
    """§3.5 #5/#6: first 10-min return beyond ±0.2%, entered 09:25, traded with the move."""
    move = momentum_return(bars)
    if move is None or abs(move) <= MOMENTUM_THRESHOLD:
        return None
    entry = _at(bars, MOMENTUM_END)
    if entry is None:
        return None
    return _make(entry.ts.date(), "mom", LONG if move > 0 else SHORT, entry, exit_)


# ── Driver ───────────────────────────────────────────────────────────────────────────────


def signals_for_day(bars: Sequence[Bar], previous_close: float | None) -> list[Signal]:
    """Every signal that triggered on one session. Days missing bars yield nothing."""
    if not bars:
        return []
    stop = exit_bar(bars)
    if stop is None:
        return []
    found = [orb(bars, stop), momentum(bars, stop)]
    if previous_close is not None:
        found += [gap_continuation(bars, previous_close, stop), gap_fade(bars, previous_close, stop)]
    return [signal for signal in found if signal is not None]


def extract_signals(sessions: Sequence[Sequence[Bar]]) -> list[Signal]:
    """Run every config over consecutive sessions, oldest first.

    ``sessions`` must be in chronological order — the previous session's last close is the
    gap reference, and the first session therefore produces no gap signals.
    """
    out: list[Signal] = []
    previous_close: float | None = None
    for bars in sessions:
        if not bars:
            continue
        out.extend(signals_for_day(bars, previous_close))
        previous_close = bars[-1].close
    return out
