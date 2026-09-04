"""Phase 2: the index-level hit-rate test — does the signal predict direction at all?

Plan doc § Phase 2 (revised). The expired-options backtest is withdrawn; this is what
replaced it, and per §5 it is now the project's only source of real statistical power.
Forward paper trading cannot supply that power — §5.2's table shows ~60 trades can only
detect a Sharpe above 4.08 — so if a signal is going to be eliminated on evidence rather
than on opinion, it is eliminated here.

**Configs are eliminated, never certified.** The gate is one-sided and deliberately hostile:
a config survives only if its out-of-sample hit rate is significantly above 50% *after*
correcting for the number of hypotheses tested. Everything else is a rejection. §3.4 predicts
few or no survivors and none is a valid result — the purpose of this file is to make that
verdict cheap to reach and impossible to fudge, not to find a winner.

Three controls, all from §5:

1. **Deflation.** Four distinct index-level hypotheses are tested (see signals.CONFIGS), so
   the p-value is Bonferroni-corrected by 4. Bonferroni rather than Šidák because the four
   signals fire on overlapping days and are plainly not independent; Bonferroni holds under
   arbitrary dependence, Šidák does not. Both are printed, the conservative one governs.
2. **Held-out tail.** The most recent 6 months are split off before anything is computed and
   are touched exactly once, for the gate. The in-sample years are diagnostic only.
3. **Walk-forward.** No parameter is fitted here — every threshold is pre-registered in §3.5 —
   so walk-forward means stability, not tuning: the in-sample span is cut into sequential
   folds and a signal that lives in one fold and dies in the others is noise wearing a hat.

Two statistics are reported per config. The **hit rate** is the gate the plan specifies. The
**mean signed return** and its t-statistic are printed alongside, because direction alone
does not pay: a 52% hit rate whose winners are smaller than its losers is worth nothing, and
the t-statistic is the quantity §5.2's power tables are denominated in. Monetisation after
§2.6's cost stack stays Phase 3's question, asked only of something that survives here.

Run::

    python -m app.options.histdata --from 2019-01-01     # once, to fill the candle cache
    python -m app.options.signal_test
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import comb, sqrt
from pathlib import Path
from statistics import fmean, stdev

from app.options.histdata import DEFAULT_CANDLE_DB, Bar, ensure_schema, load_days
from app.options.signals import CONFIGS, Signal, extract_signals

# ── Test parameters, fixed before the first run ──────────────────────────────────────────

#: Months of the most recent history held out of every diagnostic and used once, for the gate.
HOLDOUT_MONTHS = 6

#: Sequential walk-forward folds over the in-sample span. Four keeps ~1 year per fold on the
#: default history, which is enough sessions per fold for the ORB signal to say anything.
WALK_FORWARD_FOLDS = 4

#: Significance level for the deflated one-sided test.
ALPHA = 0.05

#: Hypotheses tested, for the multiple-comparisons correction. Four, not six: see the module
#: docstring of app.options.signals for why the naked/synthetic pairs are one hypothesis each.
NUM_HYPOTHESES = len(CONFIGS)


# ── Statistics ───────────────────────────────────────────────────────────────────────────


def binomial_p_at_least(hits: int, n: int) -> float:
    """Exact one-sided P(X >= hits) for X ~ Binomial(n, 0.5).

    Exact rather than normal-approximated: the gap configs fire on few enough days that the
    approximation's tail error is the same order as the effect being tested.
    """
    if n <= 0:
        return 1.0
    hits = max(0, min(hits, n))
    return sum(comb(n, i) for i in range(hits, n + 1)) / 2**n


def bonferroni(p: float, hypotheses: int = NUM_HYPOTHESES) -> float:
    """Family-wise corrected p-value, valid under arbitrary dependence between the tests."""
    return min(1.0, p * hypotheses)


def sidak(p: float, hypotheses: int = NUM_HYPOTHESES) -> float:
    """Family-wise corrected p-value assuming independent tests — printed for contrast only."""
    return 1.0 - (1.0 - p) ** hypotheses


@dataclass(frozen=True)
class Result:
    """One config's performance over one span of sessions."""

    config: str
    label: str
    sessions: int
    n: int
    hits: int

    mean_return: float  # signed, fraction of index level
    return_t: float
    mean_points: float

    @property
    def hit_rate(self) -> float:
        return self.hits / self.n if self.n else 0.0

    @property
    def trigger_rate(self) -> float:
        return self.n / self.sessions if self.sessions else 0.0

    @property
    def z(self) -> float:
        """Standard normal score of the hit rate against a fair coin."""
        return (self.hit_rate - 0.5) / sqrt(0.25 / self.n) if self.n else 0.0

    @property
    def p_raw(self) -> float:
        return binomial_p_at_least(self.hits, self.n)

    @property
    def p_deflated(self) -> float:
        return bonferroni(self.p_raw)

    @property
    def survives(self) -> bool:
        """The §Phase 2 gate: above 50%, and significantly so after deflation."""
        return self.n > 0 and self.hit_rate > 0.5 and self.p_deflated < ALPHA


def summarise(config: str, label: str, signals: Sequence[Signal], sessions: int) -> Result:
    """Collapse one config's signals over one span into a Result."""
    picked = [signal for signal in signals if signal.config == config]
    returns = [signal.signed_return for signal in picked]
    points = [signal.direction * (signal.exit - signal.entry) for signal in picked]
    n = len(picked)

    mean_return = fmean(returns) if returns else 0.0
    # t = (mean / sd) * sqrt(n) — the per-trade Sharpe scaled by root-N of Sec 5.2.
    spread = stdev(returns) if n > 1 else 0.0
    return_t = (mean_return / spread) * sqrt(n) if spread > 0 else 0.0

    return Result(
        config=config,
        label=label,
        sessions=sessions,
        n=n,
        hits=sum(1 for signal in picked if signal.hit),
        mean_return=mean_return,
        return_t=return_t,
        mean_points=fmean(points) if points else 0.0,
    )


# ── Splitting ────────────────────────────────────────────────────────────────────────────


def holdout_start(last_session: date, months: int = HOLDOUT_MONTHS) -> date:
    """First day of the held-out tail: ``months`` calendar months before the last session."""
    month_index = last_session.month - 1 - months
    year = last_session.year + month_index // 12
    month = month_index % 12 + 1
    day = min(last_session.day, 28)  # clamp so the month arithmetic never overflows February
    return date(year, month, day)


def fold_bounds(days: Sequence[date], folds: int = WALK_FORWARD_FOLDS) -> list[tuple[date, date]]:
    """Split a chronological list of session dates into ``folds`` near-equal spans."""
    if not days or folds <= 0:
        return []
    size = len(days) / folds
    bounds = []
    for i in range(folds):
        lo = days[int(i * size)]
        hi = days[min(int((i + 1) * size) - 1, len(days) - 1)]
        bounds.append((lo, hi))
    return bounds


def _in_span(signals: Sequence[Signal], lo: date, hi: date) -> list[Signal]:
    """Signals with ``lo <= day <= hi``."""
    return [signal for signal in signals if lo <= signal.day <= hi]


def _before(signals: Sequence[Signal], split: date) -> list[Signal]:
    """Signals strictly before the held-out tail. The boundary belongs to the holdout."""
    return [signal for signal in signals if signal.day < split]


# ── Reporting ────────────────────────────────────────────────────────────────────────────


def _row(result: Result) -> str:
    return (
        f"  {result.label:<22} n={result.n:>5}  trig={result.trigger_rate:>6.1%}  "
        f"hit={result.hit_rate:>6.2%}  z={result.z:>+6.2f}  "
        f"ret={result.mean_return:>+8.4%}  t={result.return_t:>+6.2f}  "
        f"pts={result.mean_points:>+7.1f}"
    )


def report(sessions: Sequence[Sequence[Bar]]) -> list[Result]:
    """Run the whole test over chronological sessions and print the verdict. Returns gate rows."""
    signals = extract_signals(sessions)
    days = [bars[0].ts.date() for bars in sessions if bars]
    if not days:
        print("no sessions in the candle cache — run app.options.histdata first")
        return []

    split = holdout_start(days[-1])
    in_sample = [day for day in days if day < split]
    out_sample = [day for day in days if day >= split]

    print("═" * 100)
    print("Phase 2 — NIFTY index-level signal test (hit rate vs a fair coin)")
    print("═" * 100)
    print(f"sessions      {len(days)}  ({days[0]} .. {days[-1]})")
    print(f"in-sample     {len(in_sample)}  ({in_sample[0]} .. {in_sample[-1]})" if in_sample else "in-sample     0")
    print(f"held out      {len(out_sample)}  ({out_sample[0]} .. {out_sample[-1]})" if out_sample else "held out    0")
    print(f"hypotheses    {NUM_HYPOTHESES} (Bonferroni), alpha {ALPHA}")
    print()

    print("── In-sample (diagnostic only — the gate does not read these) ──")
    for config in CONFIGS:
        result = summarise(config, config, _before(signals, split), len(in_sample))
        print(_row(result))
    print()

    print("── Walk-forward folds, in-sample (stability, not tuning) ──")
    for config in CONFIGS:
        print(f"  {config}:")
        for lo, hi in fold_bounds(in_sample):
            span_sessions = sum(1 for day in in_sample if lo <= day <= hi)
            result = summarise(config, f"{lo} .. {hi}", _in_span(signals, lo, hi), span_sessions)
            print(_row(result))
    print()

    print(f"── HELD OUT: last {HOLDOUT_MONTHS} months — this is the gate ──")
    gate = []
    for config in CONFIGS:
        result = summarise(config, config, _in_span(signals, split, days[-1]), len(out_sample))
        gate.append(result)
        print(_row(result))
        print(
            f"    p(one-sided)={result.p_raw:.4f}  Bonferroni={result.p_deflated:.4f}  "
            f"Sidak={sidak(result.p_raw):.4f}  ->  "
            f"{'SURVIVES' if result.survives else 'ELIMINATED'}"
        )
    print()

    survivors = [result.config for result in gate if result.survives]
    print("── Verdict ──")
    if survivors:
        print(f"  survives the gate: {', '.join(survivors)}")
        print("  Survival is not a licence to trade it: this test carries no spread, no cost")
        print("  stack and no option greeks. Phase 3 asks whether it pays after Sec 2.6.")
    else:
        print("  no config survives. Per Sec 3.4 this is the expected outcome and a valid result.")
        print("  Configs are eliminated, never certified — none of the four may go to Phase 3")
        print("  as a live candidate. One of them still ships as Phase 3's known-bad control.")
    print("═" * 100)
    return gate


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 2 index-level hit-rate test (read only)")
    parser.add_argument("--db", type=Path, default=DEFAULT_CANDLE_DB, help="candle cache from app.options.histdata")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, default=None)
    parser.add_argument("--to", dest="end", type=date.fromisoformat, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.db.exists():
        print(f"no candle cache at {args.db} — run: python -m app.options.histdata")
        return 1
    conn = sqlite3.connect(args.db)
    ensure_schema(conn)
    sessions = list(load_days(conn, args.start, args.end))
    conn.close()
    report(sessions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
