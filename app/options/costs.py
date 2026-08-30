"""Itemised Indian cost stack for NSE index options and index futures, keyed by trade date.

Every rate that has changed is stored as a date-keyed regime with the governing instrument
cited inline. Nothing is a bare literal. A backtest that spans a rate change must charge the
rate that was actually in force on the trade date.

The shared machinery (Decimal arithmetic, per-line itemisation, GST base, STT whole-rupee
rounding, transaction-charge/IPFT bundling) is validated to the paisa against a real Zerodha
contract note — a Jun-2024 BANKNIFTY futures note; see REAL_CONTRACT_NOTES in
tests/test_options_costs.py. The futures path exists for exactly two reasons: that
validation, and the synthetic-with-a-futures-leg case docs/options-paper-trading-plan.md
Sec 2.6 mentions.

All arithmetic is ``Decimal``. Floats cannot reproduce a contract note to the paisa and are
deliberately not used anywhere below; ``float`` inputs are converted via ``str`` so that a
caller passing 146.35 gets ``Decimal("146.35")`` and not the binary approximation.

Components
----------
Brokerage
    Zerodha: flat Rs 20 per executed order for equity F&O. Source: https://zerodha.com/charges/
STT / CTT
    Sale of an option: charged on the *premium*, sell side only. Rate history below.
    Exercised (ITM at expiry) options: charged on *intrinsic value*, buyer side.
    Source: Securities Transaction Tax Act 2004 as amended; see per-regime citations.
Exchange transaction charge
    NSE, on premium turnover, both sides. Rate history below.
NSE IPFT
    Investor Protection Fund Trust contribution, on premium turnover, each side.
SEBI turnover fee
    Rs 10 per crore of premium turnover, both sides.
Stamp duty
    Uniform (Indian Stamp Act as amended by Finance Act 2019, in force 01-Jul-2020):
    0.003% / Rs 300 per crore, **buy side only**, on premium turnover.
GST
    18% (9% CGST + 9% SGST). Applied to brokerage + SEBI turnover fee + exchange transaction
    charge + IPFT. It is *not* applied to STT or to stamp duty (both are themselves taxes).

Reconciliation against the worked example in docs/options-paper-trading-plan.md Sec 2.6 is
covered by the tests; the two documented discrepancies are noted at ``IPFT_REGIMES`` and in
the test module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

# ── Helpers ──────────────────────────────────────────────────────────────────────────────

_ZERO = Decimal("0")
_PAISA = Decimal("0.01")
_RUPEE = Decimal("1")
_HUNDRED = Decimal("100")
_CRORE = Decimal("10000000")


def _dec(value: Decimal | float | int | str) -> Decimal:
    """Convert to Decimal without inheriting binary float error."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _paisa(value: Decimal) -> Decimal:
    """Round to two decimal places, half up (the convention on Indian contract notes)."""
    return value.quantize(_PAISA, rounding=ROUND_HALF_UP)


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


# ── Brokerage ────────────────────────────────────────────────────────────────────────────

#: Zerodha equity F&O brokerage: flat Rs 20 per executed order, regardless of turnover.
#: Source: https://zerodha.com/charges/ (Equity F&O, "Flat Rs. 20 per executed order").
#: CONFIDENCE: high. Unchanged across the whole window covered here.
BROKERAGE_PER_ORDER: Decimal = Decimal("20")


# ── Date-keyed regime machinery ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RateRegime:
    """A rate in force for trades executed on or after ``effective_from``."""

    effective_from: date
    rate: Decimal
    source: str


def _rate_on(regimes: Sequence[RateRegime], trade_date: date, what: str) -> RateRegime:
    chosen: RateRegime | None = None
    for regime in regimes:
        if trade_date >= regime.effective_from:
            chosen = regime
    if chosen is None:
        raise ValueError(f"No {what} regime encoded for {trade_date.isoformat()}")
    return chosen


# ── STT on sale of options ───────────────────────────────────────────────────────────────

# Charged on the PREMIUM, on the SELL side only, for options that are sold (not exercised).
#
# Rate history (fraction of premium, not percent):
#   0.05%    from 01-Jun-2016 : Finance Act 2016 raised STT on sale of option from 0.017%.
#   0.0625%  from 01-Apr-2023 : Finance Act 2023 (as corrected by the official amendment of
#                               24-Mar-2023, which fixed the 0.062%/0.0625% drafting error).
#   0.10%    from 01-Oct-2024 : Finance (No. 2) Act 2024.
#   0.15%    from 01-Apr-2026 : Finance Act 2026; notified by NSE circular NSE/FATAX/73524
#                               (Ref 02/2026) dated 31-Mar-2026.
# CONFIDENCE: high for the 2024 and 2026 changes (both traced to a Finance Act plus an NSE
# tax circular). High for 01-Apr-2023. Medium-high for the 2016 rate, which predates anything
# this project will backtest.
STT_SELL_PREMIUM_REGIMES: tuple[RateRegime, ...] = (
    RateRegime(date(2016, 6, 1), Decimal("0.0005"), "Finance Act 2016 (0.05% of premium, sell side)"),
    RateRegime(date(2023, 4, 1), Decimal("0.000625"), "Finance Act 2023 (0.0625% of premium, sell side)"),
    RateRegime(date(2024, 10, 1), Decimal("0.0010"), "Finance (No. 2) Act 2024 (0.10% of premium, sell side)"),
    RateRegime(date(2026, 4, 1), Decimal("0.0015"), "Finance Act 2026; NSE/FATAX/73524 dated 31-Mar-2026 (0.15%)"),
)

# STT on an option that is exercised: charged on INTRINSIC VALUE, buyer side.
#   0.125%   from 01-Sep-2019 (settlement price basis clarified)
#   0.15%    from 01-Apr-2026 : Finance Act 2026, same circular as above.
# CONFIDENCE: high for the current rate; the exercise leg is not used by the intraday strategy
# (we never hold to expiry) but is encoded so an expiry-holding variant cannot silently omit it.
STT_EXERCISE_INTRINSIC_REGIMES: tuple[RateRegime, ...] = (
    RateRegime(date(2019, 9, 1), Decimal("0.00125"), "0.125% of intrinsic value on exercise, buyer side"),
    RateRegime(date(2026, 4, 1), Decimal("0.0015"), "Finance Act 2026; NSE/FATAX/73524 dated 31-Mar-2026 (0.15%)"),
)

#: Zerodha bills STT rounded to the NEAREST RUPEE. Broker-confirmed: the real Jun-2024
#: BANKNIFTY futures contract note computes to exactly Rs 90.90 and bills Rs 91.00. STT is
#: collected in whole rupees (Chapter VII, Finance (No. 2) Act 2004 rounding convention), and
#: the rounding is applied to the note-level (daily aggregate) STT; for a single trade per day
#: — the only case this project produces — per-leg rounding is identical. Pass
#: ``stt_rupee_rounding=False`` to :func:`leg_costs` to reproduce model tables that keep paisa
#: precision, e.g. the plan doc's Sec 2.6 table (which does NOT apply this rounding).
STT_ROUNDS_TO_RUPEE: bool = True


# ── NSE exchange transaction charge (equity options, on premium) ─────────────────────────

# Charged on premium turnover, BOTH sides.
#   0.053%    up to 30-Sep-2024  : NSE slab structure, effective rate as published by brokers.
#                                  CONFIDENCE: medium — this is the broker-published effective
#                                  rate rather than a single circular line item.
#   0.03503%  from 01-Oct-2024   : NSE circular NSE/FA/64323 dated 27-Sep-2024, issued under
#                                  SEBI/HO/MRD/TPD-1/P/CIR/2024/92 dated 01-Jul-2024 ("uniform
#                                  and equal charge structure for all members"). Rs 3,503 per
#                                  crore of premium.  CONFIDENCE: high.
#   0.0355299% from 01-Mar-2026  : NSE circular NSE/FA/73061 dated 27-Feb-2026 (primary PDF
#                                  read): transaction charge Rs 3,552.99 per crore of premium,
#                                  IPFT rolled back to Rs 0.01 per crore, explicitly "ensuring
#                                  no impact in the overall outflow" (total exactly Rs 3,553
#                                  per crore = 0.03553%).  CONFIDENCE: high.
#                                  RESOLVED (formerly a PRECISION NOTE): brokers publish the
#                                  rounded 0.03553% because they bill the transaction charge
#                                  and IPFT as ONE bundled "Exchange transaction charges" line
#                                  — proven by the real Jun-2024 futures contract note, whose
#                                  txn line equals txn + IPFT to the paisa. Circular-exact
#                                  rates are therefore encoded here, and the bundle a note
#                                  actually prints is exposed as CostBreakdown.txn_plus_ipft
#                                  (Rs 3,552.99 + Rs 0.01 = Rs 3,553/crore exactly).
NSE_TXN_CHARGE_REGIMES: tuple[RateRegime, ...] = (
    RateRegime(date(2016, 1, 1), Decimal("0.00053"), "NSE slab structure, broker-published effective rate 0.053%"),
    RateRegime(date(2024, 10, 1), Decimal("0.0003503"), "NSE/FA/64323 dated 27-Sep-2024 (Rs 3,503 per crore)"),
    RateRegime(date(2026, 3, 1), Decimal("0.000355299"), "NSE/FA/73061 dated 27-Feb-2026 (Rs 3,552.99 per crore)"),
)


# ── NSE Investor Protection Fund Trust (IPFT) ────────────────────────────────────────────

# Charged on premium turnover, each side, expressed per crore.
#   Rs 0.01/crore   baseline    : the pre-01-Apr-2023 level.
#   Rs 50/crore     01-Apr-2023 : NSE circular NSE/FA/56129 raised the equity-options IPFT
#                                 contribution by Rs 49.99 per crore of premium to replenish
#                                 the corpus.
#   Rs 0.01/crore   01-Mar-2026 : NSE circular NSE/FA/73061 rolled it back; the transaction
#                                 charge above absorbed the difference.
# CONFIDENCE: high for the rollback date and amount; medium-high for the Apr-2023 increase.
#
# DISCREPANCY NOTE: docs/options-paper-trading-plan.md Sec 2.6 lists IPFT as "Rs 0.01" as an
# *amount* in a worked example whose premium turnover is Rs 18,980. At Rs 0.01 per crore the
# actual amount is Rs 0.0000190, i.e. effectively zero. The doc's Sec 2.6 grand total of
# Rs 69.71 is therefore one paisa high; the correct total for that example is Rs 69.70. This
# module computes the rate correctly and the test suite asserts Rs 69.70, with the one-paisa
# difference documented rather than papered over.
IPFT_PER_CRORE_REGIMES: tuple[RateRegime, ...] = (
    RateRegime(date(2016, 1, 1), Decimal("0.01"), "pre-Apr-2023 baseline, Rs 0.01 per crore of premium"),
    RateRegime(date(2023, 4, 1), Decimal("50"), "NSE/FA/56129 dated Mar-2023 (Rs 50 per crore of premium)"),
    RateRegime(date(2026, 3, 1), Decimal("0.01"), "NSE/FA/73061 rollback to Rs 0.01 per crore, eff. 01-Mar-2026"),
)


# ── SEBI turnover fee ────────────────────────────────────────────────────────────────────

#: Rs 10 per crore of premium turnover, both sides.
#: Source: SEBI (Stock Brokers) Regulations fee schedule; published by every broker as
#: "SEBI charges: Rs 10 / crore". CONFIDENCE: high, unchanged across the covered window.
SEBI_TURNOVER_PER_CRORE: Decimal = Decimal("10")


# ── Stamp duty ───────────────────────────────────────────────────────────────────────────

#: 0.003% (Rs 300 per crore) of premium turnover, BUY side only.
#: Source: Indian Stamp Act 1899 as amended by Finance Act 2019, uniform rates in force from
#: 01-Jul-2020. CONFIDENCE: high, unchanged across the covered window.
STAMP_DUTY_BUY_RATE: Decimal = Decimal("0.00003")


# ── GST ──────────────────────────────────────────────────────────────────────────────────

#: 18% (9% CGST + 9% SGST) on brokerage and on the exchange/regulatory service charges.
#: CONFIDENCE: high. The 2025 GST rate rationalisation left financial services at 18%.
GST_RATE: Decimal = Decimal("0.18")


# ── Index futures (NIFTY / BANKNIFTY) ────────────────────────────────────────────────────
#
# The futures path exists to (a) validate the shared cost machinery against the real Jun-2024
# BANKNIFTY futures contract note and (b) price the synthetic-with-a-futures-leg case the plan
# doc's Sec 2.6 mentions. All futures charges are on TRADED (contract) VALUE, not premium.

#: Zerodha equity futures brokerage: 0.03% of turnover or Rs 20 per executed order, whichever
#: is LOWER. Source: https://zerodha.com/charges/ ("0.03% or Rs. 20/executed order whichever
#: is lower"). At index-futures contract values (1 lot BANKNIFTY ~Rs 7L) 0.03% is ~Rs 218, so
#: the Rs 20 cap always binds in practice; the real Jun-2024 note bills exactly Rs 20.00.
#: CONFIDENCE: high.
FUTURES_BROKERAGE_RATE: Decimal = Decimal("0.0003")

# STT on the sale of a futures contract: charged on traded value, SELL side only.
#   0.01%    from 01-Jun-2013 : Finance Act 2013 (cut from 0.017%). Predates anything this
#                               project will backtest. CONFIDENCE: medium-high.
#   0.0125%  from 01-Apr-2023 : Finance Act 2023. VALIDATED: the real Jun-2024 note computes
#                               727,200 x 0.0125% = Rs 90.90, billed Rs 91.00 (whole-rupee
#                               STT rounding). CONFIDENCE: high.
#   0.02%    from 01-Oct-2024 : Finance (No. 2) Act 2024. CONFIDENCE: high.
#   0.05%    from 01-Apr-2026 : Finance Act 2026; NSE/FATAX/73524 (Ref 02/2026) dated
#                               31-Mar-2026, quoted in plan doc Sec 2.6. CONFIDENCE: high.
FUT_STT_SELL_REGIMES: tuple[RateRegime, ...] = (
    RateRegime(date(2013, 6, 1), Decimal("0.0001"), "Finance Act 2013 (0.01% of traded value, sell side)"),
    RateRegime(date(2023, 4, 1), Decimal("0.000125"), "Finance Act 2023 (0.0125%); validated by Jun-2024 note"),
    RateRegime(date(2024, 10, 1), Decimal("0.0002"), "Finance (No. 2) Act 2024 (0.02% of traded value, sell side)"),
    RateRegime(date(2026, 4, 1), Decimal("0.0005"), "Finance Act 2026; NSE/FATAX/73524 dated 31-Mar-2026 (0.05%)"),
)

# NSE exchange transaction charge, equity futures, on traded value, both sides.
#   0.00198%   up to 31-Mar-2023 : DERIVED, not read from a circular — NSE/FA/56129 states the
#                                  charge was "reduced ... by Rs. 10 per crore" on 01-Apr-2023,
#                                  and the post-reduction figure of Rs 188/crore is validated
#                                  by the note below, so the prior level was Rs 198/crore.
#                                  CONFIDENCE: medium (derived; predates the backtest window).
#   0.00188%   from 01-Apr-2023  : broker-billed effective rate under the slab structure.
#                                  VALIDATED to the paisa by the real Jun-2024 note: the
#                                  "Exchange transaction charges" line of Rs 14.40 is exactly
#                                  727,200 x 0.00188% + Rs 10/crore IPFT (13.67136 + 0.7272 =
#                                  14.39856). CONFIDENCE: high for Zerodha notes; the top-slab
#                                  members paid less under the pre-Oct-2024 slabs.
#   0.00173%   from 01-Oct-2024  : NSE/FA/64323 dated 27-Sep-2024 (Rs 173 per crore, uniform
#                                  under SEBI True-to-Label). CONFIDENCE: high.
#   0.0018299% from 01-Mar-2026  : NSE/FA/73061 dated 27-Feb-2026 (primary PDF read):
#                                  Rs 182.99 per crore, IPFT rolled back to Rs 0.01/crore,
#                                  total outflow unchanged at Rs 183/crore. CONFIDENCE: high.
FUT_TXN_CHARGE_REGIMES: tuple[RateRegime, ...] = (
    RateRegime(date(2016, 1, 1), Decimal("0.0000198"), "derived: Rs 188/crore + NSE/FA/56129's Rs 10/crore cut"),
    RateRegime(date(2023, 4, 1), Decimal("0.0000188"), "broker-billed slab rate; validated by Jun-2024 note"),
    RateRegime(date(2024, 10, 1), Decimal("0.0000173"), "NSE/FA/64323 dated 27-Sep-2024 (Rs 173 per crore)"),
    RateRegime(date(2026, 3, 1), Decimal("0.000018299"), "NSE/FA/73061 dated 27-Feb-2026 (Rs 182.99 per crore)"),
)

# NSE IPFT, equity futures, on traded value, each side, expressed per crore.
#   Rs 0.01/crore  baseline    : NSE/FA/73061 recital — the Apr-2023 enhancement was "by
#                                Rs. 9.99 per crore" and the 2026 rollback is "at the level
#                                levied prior to April 1, 2023", i.e. Rs 0.01/crore.
#   Rs 10/crore    01-Apr-2023 : NSE/FA/56129 dated 24-Mar-2023 (cash + equity futures raised
#                                to Rs 10/crore; options to Rs 50/crore). VALIDATED by the
#                                Jun-2024 note (bundled into the txn line, see above).
#   Rs 0.01/crore  01-Mar-2026 : NSE/FA/73061 rollback, same event as the txn-charge rise.
# CONFIDENCE: high for all three (FA/73061 read as primary; FA/56129 corroborated by its
# recital and by the contract note).
FUT_IPFT_PER_CRORE_REGIMES: tuple[RateRegime, ...] = (
    RateRegime(date(2016, 1, 1), Decimal("0.01"), "pre-Apr-2023 baseline per NSE/FA/73061 recital"),
    RateRegime(date(2023, 4, 1), Decimal("10"), "NSE/FA/56129 dated 24-Mar-2023 (Rs 10 per crore, futures)"),
    RateRegime(date(2026, 3, 1), Decimal("0.01"), "NSE/FA/73061 rollback to Rs 0.01 per crore, eff. 01-Mar-2026"),
)

#: Stamp duty on futures: 0.002% (Rs 200 per crore) of traded value, BUY side only. Futures
#: carry a LOWER rate than the 0.003% on options — Indian Stamp Act 1899 as amended by Finance
#: Act 2019, uniform rates in force from 01-Jul-2020 (futures: 0.002%; options: 0.003%).
#: The Jun-2024 note is a sell, so it does not exercise this rate. CONFIDENCE: high (published
#: schedule), but not yet note-validated.
STAMP_DUTY_BUY_RATE_FUTURES: Decimal = Decimal("0.00002")


# ── Output types ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CostLine:
    """One line of a contract note."""

    name: str
    amount: Decimal
    """Unrounded amount. Round with :meth:`rounded` for display / comparison."""

    basis: str
    """Human-readable description of what the amount was computed from."""

    source: str
    """Citation for the rate used."""

    @property
    def rounded(self) -> Decimal:
        return _paisa(self.amount)


@dataclass(frozen=True)
class CostBreakdown:
    """Itemised cost stack, designed to be diffed line-by-line against a real contract note."""

    lines: tuple[CostLine, ...]

    @property
    def total(self) -> Decimal:
        """Total from unrounded line amounts, rounded once at the end."""
        return _paisa(sum((line.amount for line in self.lines), _ZERO))

    @property
    def total_of_rounded_lines(self) -> Decimal:
        """Total of the per-line rounded amounts.

        Brokers differ on whether they round per line or once at the end; expose both so a
        contract-note comparison can identify which convention the broker used.
        """
        return _paisa(sum((line.rounded for line in self.lines), _ZERO))

    @property
    def txn_plus_ipft(self) -> Decimal:
        """Exchange transaction charge + IPFT, summed unrounded then rounded once.

        Zerodha bills these as ONE bundled "Exchange transaction charges" line — proven by the
        real Jun-2024 futures note (Rs 14.40 = 13.67136 txn + 0.7272 IPFT). Diff this, not the
        two components separately, against a contract note.
        """
        bundled = sum((line.amount for line in self.lines if line.name in (EXCHANGE_TXN, IPFT)), _ZERO)
        return _paisa(bundled)

    def as_dict(self) -> dict[str, Decimal]:
        """Line name -> rounded amount. Convenient for assertion diffs."""
        return {line.name: line.rounded for line in self.lines}

    def get(self, name: str) -> Decimal:
        for line in self.lines:
            if line.name == name:
                return line.amount
        raise KeyError(name)

    def __add__(self, other: CostBreakdown) -> CostBreakdown:
        return CostBreakdown(lines=self.lines + other.lines)


# ── Line names (stable identifiers used by tests and by contract-note diffs) ─────────────

BROKERAGE = "brokerage"
STT = "stt"
EXCHANGE_TXN = "exchange_transaction_charge"
IPFT = "ipft"
SEBI_FEE = "sebi_turnover_fee"
STAMP_DUTY = "stamp_duty"
GST = "gst"

#: Components on which GST is levied. STT and stamp duty are excluded (they are taxes, not
#: services). BROKER-CONFIRMED by the real Jun-2024 futures contract note: its GST line reads
#: "CGST/SGST @9% of (Brok, SEBI, Trans & Clearing)", and the printed Rs 3.16 + Rs 3.16 is
#: only reproducible with SEBI and the bundled txn+IPFT in the base — excluding SEBI would
#: give Rs 3.10 + Rs 3.10. (The note cannot discriminate rounded-base vs unrounded-base GST:
#: both give 3.16/3.16 there. Unrounded is used, matching the end-of-note rounding convention.)
GST_BASE_COMPONENTS: frozenset[str] = frozenset({BROKERAGE, SEBI_FEE, EXCHANGE_TXN, IPFT})


# ── Core computation ─────────────────────────────────────────────────────────────────────


def leg_costs(
    *,
    trade_date: date,
    side: Side,
    premium: Decimal | float | int | str,
    quantity: int,
    orders: int = 1,
    stt_rupee_rounding: bool = STT_ROUNDS_TO_RUPEE,
) -> CostBreakdown:
    """Itemised costs for one executed leg of an index-option trade.

    ``premium`` is the per-unit option price in rupees; ``quantity`` is the total number of
    units (lots x lot size), not the number of lots. ``orders`` is the number of executed
    orders the leg was filled in — brokerage is per executed order, so a leg split across two
    orders costs Rs 40 of brokerage, not Rs 20.

    ``stt_rupee_rounding`` (default on, per :data:`STT_ROUNDS_TO_RUPEE`) rounds STT to the
    nearest rupee the way Zerodha bills it; pass ``False`` to keep the exact statutory amount,
    e.g. when reproducing the plan doc's Sec 2.6 model table.

    Returns every component including zero-valued ones, so the breakdown always has the same
    shape and can be diffed positionally against a contract note.
    """
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if orders <= 0:
        raise ValueError("orders must be positive")

    premium_dec = _dec(premium)
    if premium_dec < _ZERO:
        raise ValueError("premium cannot be negative")

    turnover = premium_dec * Decimal(quantity)

    brokerage = BROKERAGE_PER_ORDER * Decimal(orders)

    stt_regime = _rate_on(STT_SELL_PREMIUM_REGIMES, trade_date, "STT")
    stt_amount = turnover * stt_regime.rate if side is Side.SELL else _ZERO
    if stt_rupee_rounding:
        stt_amount = stt_rounded_to_rupee(stt_amount)

    txn_regime = _rate_on(NSE_TXN_CHARGE_REGIMES, trade_date, "NSE transaction charge")
    txn_amount = turnover * txn_regime.rate

    ipft_regime = _rate_on(IPFT_PER_CRORE_REGIMES, trade_date, "IPFT")
    ipft_amount = turnover * ipft_regime.rate / _CRORE

    sebi_amount = turnover * SEBI_TURNOVER_PER_CRORE / _CRORE

    stamp_amount = turnover * STAMP_DUTY_BUY_RATE if side is Side.BUY else _ZERO

    pre_gst = {
        BROKERAGE: brokerage,
        SEBI_FEE: sebi_amount,
        EXCHANGE_TXN: txn_amount,
        IPFT: ipft_amount,
    }
    gst_amount = sum((v for k, v in pre_gst.items() if k in GST_BASE_COMPONENTS), _ZERO) * GST_RATE

    side_label = side.value.lower()
    return CostBreakdown(
        lines=(
            CostLine(
                BROKERAGE,
                brokerage,
                f"Rs {BROKERAGE_PER_ORDER} x {orders} executed order(s)",
                "Zerodha equity F&O: flat Rs 20 per executed order",
            ),
            CostLine(
                STT,
                stt_amount,
                (
                    f"{stt_regime.rate * _HUNDRED}% of Rs {turnover} premium turnover (sell side)"
                    + (", rounded to the nearest rupee" if stt_rupee_rounding else "")
                    if side is Side.SELL
                    else "not levied on the buy side"
                ),
                stt_regime.source,
            ),
            CostLine(
                EXCHANGE_TXN,
                txn_amount,
                f"{txn_regime.rate * _HUNDRED}% of Rs {turnover} premium turnover ({side_label} side)",
                txn_regime.source,
            ),
            CostLine(
                IPFT,
                ipft_amount,
                f"Rs {ipft_regime.rate} per crore of Rs {turnover} premium turnover ({side_label} side)",
                ipft_regime.source,
            ),
            CostLine(
                SEBI_FEE,
                sebi_amount,
                f"Rs {SEBI_TURNOVER_PER_CRORE} per crore of Rs {turnover} premium turnover",
                "SEBI (Stock Brokers) Regulations turnover fee, Rs 10 per crore",
            ),
            CostLine(
                STAMP_DUTY,
                stamp_amount,
                (
                    f"{STAMP_DUTY_BUY_RATE * _HUNDRED}% of Rs {turnover} premium turnover (buy side)"
                    if side is Side.BUY
                    else "not levied on the sell side"
                ),
                "Indian Stamp Act as amended by Finance Act 2019, uniform rates from 01-Jul-2020",
            ),
            CostLine(
                GST,
                gst_amount,
                f"{GST_RATE * _HUNDRED}% of ({' + '.join(sorted(GST_BASE_COMPONENTS))})",
                "CGST 9% + SGST 9% on brokerage and exchange/regulatory service charges",
            ),
        )
    )


def round_trip_costs(
    *,
    entry_date: date,
    entry_premium: Decimal | float | int | str,
    exit_date: date,
    exit_premium: Decimal | float | int | str,
    quantity: int,
    entry_side: Side = Side.BUY,
    entry_orders: int = 1,
    exit_orders: int = 1,
    stt_rupee_rounding: bool = STT_ROUNDS_TO_RUPEE,
) -> CostBreakdown:
    """Combined itemised costs for a complete round trip.

    ``entry_side`` defaults to BUY (long option). Pass ``Side.SELL`` for a short-option entry;
    the exit is always the opposite side.

    Line names repeat (one set per leg). Use :meth:`CostBreakdown.total` for the aggregate, or
    :func:`aggregate_by_name` to collapse the two legs into one line per component.
    """
    exit_side = Side.SELL if entry_side is Side.BUY else Side.BUY
    entry = leg_costs(
        trade_date=entry_date,
        side=entry_side,
        premium=entry_premium,
        quantity=quantity,
        orders=entry_orders,
        stt_rupee_rounding=stt_rupee_rounding,
    )
    exit_leg = leg_costs(
        trade_date=exit_date,
        side=exit_side,
        premium=exit_premium,
        quantity=quantity,
        orders=exit_orders,
        stt_rupee_rounding=stt_rupee_rounding,
    )
    return entry + exit_leg


def futures_leg_costs(
    *,
    trade_date: date,
    side: Side,
    price: Decimal | float | int | str,
    quantity: int,
    orders: int = 1,
    stt_rupee_rounding: bool = STT_ROUNDS_TO_RUPEE,
) -> CostBreakdown:
    """Itemised costs for one executed leg of an index-futures trade (NIFTY / BANKNIFTY).

    Exists for two purposes only: validating the shared cost machinery against the real
    Jun-2024 BANKNIFTY futures contract note, and pricing the synthetic-with-a-futures-leg
    case docs/options-paper-trading-plan.md Sec 2.6 mentions. All charges are on TRADED VALUE
    (price x quantity), not premium. ``price`` is the per-unit traded price; ``quantity`` is
    total units (lots x lot size).

    Line names are shared with :func:`leg_costs`, so :class:`CostBreakdown` diffing,
    :attr:`CostBreakdown.txn_plus_ipft` and :func:`aggregate_by_name` work identically.
    """
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if orders <= 0:
        raise ValueError("orders must be positive")

    price_dec = _dec(price)
    if price_dec < _ZERO:
        raise ValueError("price cannot be negative")

    turnover = price_dec * Decimal(quantity)

    # Rs 20 per executed order or 0.03% of that order's turnover, whichever is lower. Orders
    # are assumed to split the quantity evenly; at index-futures contract values the Rs 20 cap
    # binds regardless, so the assumption is immaterial in practice.
    per_order_turnover = turnover / Decimal(orders)
    brokerage = min(per_order_turnover * FUTURES_BROKERAGE_RATE, BROKERAGE_PER_ORDER) * Decimal(orders)

    stt_regime = _rate_on(FUT_STT_SELL_REGIMES, trade_date, "futures STT")
    stt_amount = turnover * stt_regime.rate if side is Side.SELL else _ZERO
    if stt_rupee_rounding:
        stt_amount = stt_rounded_to_rupee(stt_amount)

    txn_regime = _rate_on(FUT_TXN_CHARGE_REGIMES, trade_date, "futures NSE transaction charge")
    txn_amount = turnover * txn_regime.rate

    ipft_regime = _rate_on(FUT_IPFT_PER_CRORE_REGIMES, trade_date, "futures IPFT")
    ipft_amount = turnover * ipft_regime.rate / _CRORE

    sebi_amount = turnover * SEBI_TURNOVER_PER_CRORE / _CRORE

    stamp_amount = turnover * STAMP_DUTY_BUY_RATE_FUTURES if side is Side.BUY else _ZERO

    pre_gst = {
        BROKERAGE: brokerage,
        SEBI_FEE: sebi_amount,
        EXCHANGE_TXN: txn_amount,
        IPFT: ipft_amount,
    }
    gst_amount = sum((v for k, v in pre_gst.items() if k in GST_BASE_COMPONENTS), _ZERO) * GST_RATE

    side_label = side.value.lower()
    return CostBreakdown(
        lines=(
            CostLine(
                BROKERAGE,
                brokerage,
                f"min({FUTURES_BROKERAGE_RATE * _HUNDRED}% of turnover, Rs {BROKERAGE_PER_ORDER}) x {orders} order(s)",
                "Zerodha equity futures: 0.03% or Rs 20 per executed order, whichever is lower",
            ),
            CostLine(
                STT,
                stt_amount,
                (
                    f"{stt_regime.rate * _HUNDRED}% of Rs {turnover} traded value (sell side)"
                    + (", rounded to the nearest rupee" if stt_rupee_rounding else "")
                    if side is Side.SELL
                    else "not levied on the buy side"
                ),
                stt_regime.source,
            ),
            CostLine(
                EXCHANGE_TXN,
                txn_amount,
                f"{txn_regime.rate * _HUNDRED}% of Rs {turnover} traded value ({side_label} side)",
                txn_regime.source,
            ),
            CostLine(
                IPFT,
                ipft_amount,
                f"Rs {ipft_regime.rate} per crore of Rs {turnover} traded value ({side_label} side)",
                ipft_regime.source,
            ),
            CostLine(
                SEBI_FEE,
                sebi_amount,
                f"Rs {SEBI_TURNOVER_PER_CRORE} per crore of Rs {turnover} traded value",
                "SEBI (Stock Brokers) Regulations turnover fee, Rs 10 per crore",
            ),
            CostLine(
                STAMP_DUTY,
                stamp_amount,
                (
                    f"{STAMP_DUTY_BUY_RATE_FUTURES * _HUNDRED}% of Rs {turnover} traded value (buy side)"
                    if side is Side.BUY
                    else "not levied on the sell side"
                ),
                "Indian Stamp Act as amended by Finance Act 2019, futures 0.002%, from 01-Jul-2020",
            ),
            CostLine(
                GST,
                gst_amount,
                f"{GST_RATE * _HUNDRED}% of ({' + '.join(sorted(GST_BASE_COMPONENTS))})",
                "CGST 9% + SGST 9%; base confirmed by the Jun-2024 note (includes SEBI and bundled txn+IPFT)",
            ),
        )
    )


def aggregate_by_name(breakdown: CostBreakdown) -> dict[str, Decimal]:
    """Collapse a multi-leg breakdown into one unrounded amount per component name."""
    totals: dict[str, Decimal] = {}
    for line in breakdown.lines:
        totals[line.name] = totals.get(line.name, _ZERO) + line.amount
    return totals


def exercise_stt(*, trade_date: date, intrinsic_value: Decimal | float | int | str, quantity: int) -> CostLine:
    """STT on an option that is exercised at expiry — charged on intrinsic value, buyer side.

    Not used by the intraday strategy, which never holds to expiry. Encoded so that a variant
    which does hold to expiry cannot silently omit it.
    """
    regime = _rate_on(STT_EXERCISE_INTRINSIC_REGIMES, trade_date, "exercise STT")
    amount = _dec(intrinsic_value) * Decimal(quantity) * regime.rate
    return CostLine(
        STT,
        amount,
        f"{regime.rate * _HUNDRED}% of intrinsic value (exercise, buyer side)",
        regime.source,
    )


def stt_rounded_to_rupee(amount: Decimal) -> Decimal:
    """STT rounded to the nearest rupee.

    BROKER-CONFIRMED: the real Jun-2024 futures contract note bills Rs 91.00 where the exact
    statutory amount is Rs 90.90, so :func:`leg_costs` and :func:`futures_leg_costs` apply
    this by default (see :data:`STT_ROUNDS_TO_RUPEE`). Also exposed directly for callers that
    aggregate several trades into one note-level STT figure before rounding.
    """
    return amount.quantize(_RUPEE, rounding=ROUND_HALF_UP)
