"""Tests for app.options.costs — the Indian cost stack for NSE index options and futures.

The Phase 0a acceptance gate is that this module reproduces a real Zerodha contract note to
the paisa. That gate is CLOSED for the shared machinery: the Jun-2024 BANKNIFTY futures note
under "REAL CONTRACT NOTE FIXTURES" below reproduces exactly. Options-specific *rate values*
remain circular-sourced until a real options note arrives — see REAL_OPTIONS_CONTRACT_NOTES.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.options.costs import (
    BROKERAGE,
    BROKERAGE_PER_ORDER,
    EXCHANGE_TXN,
    FUT_IPFT_PER_CRORE_REGIMES,
    FUT_STT_SELL_REGIMES,
    FUT_TXN_CHARGE_REGIMES,
    FUTURES_BROKERAGE_RATE,
    GST,
    GST_BASE_COMPONENTS,
    GST_RATE,
    IPFT,
    IPFT_PER_CRORE_REGIMES,
    NSE_TXN_CHARGE_REGIMES,
    SEBI_FEE,
    SEBI_TURNOVER_PER_CRORE,
    STAMP_DUTY,
    STAMP_DUTY_BUY_RATE,
    STAMP_DUTY_BUY_RATE_FUTURES,
    STT,
    STT_ROUNDS_TO_RUPEE,
    STT_SELL_PREMIUM_REGIMES,
    CostBreakdown,
    Side,
    aggregate_by_name,
    exercise_stt,
    futures_leg_costs,
    leg_costs,
    round_trip_costs,
    stt_rounded_to_rupee,
)

# ── Helpers ──────────────────────────────────────────────────────────────────────────────

#: A trade date after every rate change encoded in the module (STT 0.15%, txn 0.0355299%,
#: IPFT Rs 0.01/crore). Matches the regime the plan doc's Sec 2.6 example assumes.
CURRENT_REGIME_DAY = date(2026, 8, 28)


def _rate_at(regimes: tuple, on: date) -> Decimal:  # type: ignore[type-arg]
    chosen = None
    for regime in regimes:
        if on >= regime.effective_from:
            chosen = regime
    assert chosen is not None
    return Decimal(chosen.rate)


# ── Regime tables ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (date(2023, 3, 31), Decimal("0.0005")),  # Finance Act 2016 regime
        (date(2023, 4, 1), Decimal("0.000625")),  # Finance Act 2023
        (date(2024, 9, 30), Decimal("0.000625")),
        (date(2024, 10, 1), Decimal("0.0010")),  # Finance (No. 2) Act 2024
        (date(2026, 3, 31), Decimal("0.0010")),
        (date(2026, 4, 1), Decimal("0.0015")),  # Finance Act 2026 / NSE/FATAX/73524
    ],
)
def test_stt_rate_history(on: date, expected: Decimal) -> None:
    assert _rate_at(STT_SELL_PREMIUM_REGIMES, on) == expected


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (date(2024, 9, 30), Decimal("0.00053")),
        (date(2024, 10, 1), Decimal("0.0003503")),  # NSE/FA/64323, SEBI True-to-Label
        (date(2026, 2, 28), Decimal("0.0003503")),
        (date(2026, 3, 1), Decimal("0.000355299")),  # NSE/FA/73061 circular-exact Rs 3,552.99/crore
    ],
)
def test_exchange_transaction_charge_history(on: date, expected: Decimal) -> None:
    assert _rate_at(NSE_TXN_CHARGE_REGIMES, on) == expected


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (date(2023, 3, 31), Decimal("0.01")),
        (date(2023, 4, 1), Decimal("50")),  # NSE/FA/56129
        (date(2026, 2, 28), Decimal("50")),
        (date(2026, 3, 1), Decimal("0.01")),  # NSE/FA/73061 rollback
    ],
)
def test_ipft_history(on: date, expected: Decimal) -> None:
    assert _rate_at(IPFT_PER_CRORE_REGIMES, on) == expected


def test_the_2026_transaction_charge_and_ipft_changes_are_the_same_event() -> None:
    # NSE/FA/73061 raised the transaction charge by EXACTLY the IPFT it removed ("ensuring no
    # impact in the overall outflow"): +Rs 49.99/crore txn, -Rs 49.99/crore IPFT. With the
    # circular-exact rate encoded, the identity holds to the paisa, and the bundled figure a
    # broker bills (txn + IPFT) is exactly Rs 3,553/crore = the published 0.03553%.
    txn_delta = (Decimal("0.000355299") - Decimal("0.0003503")) * Decimal("10000000")
    ipft_delta = Decimal("50") - Decimal("0.01")
    assert txn_delta == ipft_delta == Decimal("49.99")
    bundle = Decimal("0.000355299") * Decimal("10000000") + Decimal("0.01")
    assert bundle == Decimal("3553.00")


def test_every_regime_carries_a_citation() -> None:
    for table in (
        STT_SELL_PREMIUM_REGIMES,
        NSE_TXN_CHARGE_REGIMES,
        IPFT_PER_CRORE_REGIMES,
        FUT_STT_SELL_REGIMES,
        FUT_TXN_CHARGE_REGIMES,
        FUT_IPFT_PER_CRORE_REGIMES,
    ):
        for regime in table:
            assert regime.source.strip(), f"regime effective {regime.effective_from} has no source"
        dates = [r.effective_from for r in table]
        assert dates == sorted(dates)


def test_rates_before_the_earliest_regime_fail_loudly() -> None:
    with pytest.raises(ValueError, match="No STT regime encoded"):
        leg_costs(trade_date=date(2010, 1, 1), side=Side.SELL, premium=100, quantity=65)


# ── Side asymmetry ───────────────────────────────────────────────────────────────────────


def test_stt_is_sell_side_only() -> None:
    buy = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65)
    sell = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    assert buy.get(STT) == Decimal("0")
    assert sell.get(STT) > 0


def test_stamp_duty_is_buy_side_only() -> None:
    buy = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65)
    sell = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    assert buy.get(STAMP_DUTY) > 0
    assert sell.get(STAMP_DUTY) == Decimal("0")


def test_both_sides_pay_exchange_regulatory_charges() -> None:
    buy = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65)
    sell = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    for component in (EXCHANGE_TXN, SEBI_FEE, IPFT, BROKERAGE, GST):
        assert buy.get(component) > 0
        assert sell.get(component) > 0


def test_breakdown_always_has_the_same_shape() -> None:
    buy = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65)
    sell = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    assert [line.name for line in buy.lines] == [line.name for line in sell.lines]
    assert len(buy.lines) == 7


# ── Component arithmetic ─────────────────────────────────────────────────────────────────


def test_brokerage_is_per_executed_order() -> None:
    one = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65, orders=1)
    three = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65, orders=3)
    assert one.get(BROKERAGE) == BROKERAGE_PER_ORDER
    assert three.get(BROKERAGE) == BROKERAGE_PER_ORDER * 3


def test_gst_base_excludes_stt_and_stamp_duty() -> None:
    assert STT not in GST_BASE_COMPONENTS
    assert STAMP_DUTY not in GST_BASE_COMPONENTS
    breakdown = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    base = sum((breakdown.get(name) for name in GST_BASE_COMPONENTS), Decimal("0"))
    assert breakdown.get(GST) == base * GST_RATE


def test_gst_base_includes_ipft() -> None:
    # Sec 2.6 of the plan writes the GST base as "18% of (brokerage+SEBI+txn)", omitting IPFT.
    # Zerodha's charge sheet lists GST on IPFT too, so IPFT is included here. At current IPFT
    # (Rs 0.01/crore) this cannot move a paisa; between 01-Apr-2023 and 28-Feb-2026 (Rs 50/crore)
    # it could, so the divergence is asserted rather than left implicit.
    assert IPFT in GST_BASE_COMPONENTS
    old_regime = leg_costs(trade_date=date(2025, 6, 10), side=Side.SELL, premium=146, quantity=65)
    without_ipft = sum(
        (old_regime.get(name) for name in GST_BASE_COMPONENTS - {IPFT}),
        Decimal("0"),
    )
    assert old_regime.get(GST) > without_ipft * GST_RATE


def test_sebi_fee_is_ten_rupees_per_crore() -> None:
    breakdown = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=Decimal("1000"), quantity=10000)
    # Turnover is exactly Rs 1 crore.
    assert breakdown.get(SEBI_FEE) == SEBI_TURNOVER_PER_CRORE


def test_stamp_duty_is_three_hundred_per_crore() -> None:
    breakdown = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=Decimal("1000"), quantity=10000)
    assert breakdown.get(STAMP_DUTY) == Decimal("300")
    assert STAMP_DUTY_BUY_RATE * Decimal("10000000") == Decimal("300")


def test_costs_scale_linearly_with_quantity_except_brokerage() -> None:
    one_lot = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    two_lots = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=130)
    for component in (STT, EXCHANGE_TXN, SEBI_FEE, IPFT):
        assert two_lots.get(component) == one_lot.get(component) * 2
    assert two_lots.get(BROKERAGE) == one_lot.get(BROKERAGE)


def test_float_premium_does_not_leak_binary_error() -> None:
    from_float = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146.35, quantity=65)
    from_str = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium="146.35", quantity=65)
    assert from_float.total == from_str.total
    assert from_float.get(STT) == from_str.get(STT)


@pytest.mark.parametrize(("quantity", "orders"), [(0, 1), (-65, 1), (65, 0), (65, -1)])
def test_invalid_inputs_are_rejected(quantity: int, orders: int) -> None:
    with pytest.raises(ValueError):
        leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=quantity, orders=orders)


def test_negative_premium_is_rejected() -> None:
    with pytest.raises(ValueError, match="premium cannot be negative"):
        leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=-1, quantity=65)


# ── Sec 2.6 worked example ───────────────────────────────────────────────────────────────

# docs/options-paper-trading-plan.md Sec 2.6: 1 lot ATM NIFTY, premium 146 points, lot 65,
# round trip. Premium turnover Rs 9,490 per leg, Rs 18,980 for the round trip.
#
# The doc's per-line figures reproduce exactly, with two documented exceptions:
#
#   1. IPFT. The doc shows "Rs 0.01" as an *amount*; Rs 0.01 is the rate *per crore*. On
#      Rs 18,980 of premium turnover the amount is Rs 0.0000190, i.e. zero to the paisa.
#   2. STT. 0.15% of Rs 9,490 is exactly Rs 14.235. Rounded half-up that is Rs 14.24; the doc
#      shows Rs 14.23, which is what a float computation truncates to.
#
# The doc's stated grand total of Rs 69.71 does not match its own line items, which sum to
# Rs 69.70. Exact Decimal arithmetic also gives Rs 69.70. That is what is asserted here.
SEC_2_6_PREMIUM = Decimal("146")
SEC_2_6_QUANTITY = 65
SEC_2_6_TOTAL = Decimal("69.70")
SEC_2_6_DOC_TOTAL = Decimal("69.71")


@pytest.fixture
def sec_2_6_round_trip() -> CostBreakdown:
    # stt_rupee_rounding=False: the doc's model table keeps STT at paisa precision (14.235 ->
    # 14.24). A real note would bill whole-rupee STT (14.235 -> 14.00, total 69.46) — see
    # test_sec_2_6_as_a_broker_would_bill_it below.
    return round_trip_costs(
        entry_date=CURRENT_REGIME_DAY,
        entry_premium=SEC_2_6_PREMIUM,
        exit_date=CURRENT_REGIME_DAY,
        exit_premium=SEC_2_6_PREMIUM,
        quantity=SEC_2_6_QUANTITY,
        stt_rupee_rounding=False,
    )


def test_sec_2_6_total(sec_2_6_round_trip: CostBreakdown) -> None:
    assert sec_2_6_round_trip.total == SEC_2_6_TOTAL
    # Same answer whether we round per line or once at the end — a good sign the figures are
    # not sitting on a knife edge.
    assert sec_2_6_round_trip.total_of_rounded_lines == SEC_2_6_TOTAL
    # Documented one-paisa disagreement with the doc's stated total.
    assert SEC_2_6_DOC_TOTAL - sec_2_6_round_trip.total == Decimal("0.01")


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        (BROKERAGE, Decimal("40.00")),
        (STT, Decimal("14.235")),  # doc rounds this to 14.23; half-up gives 14.24
        (EXCHANGE_TXN, Decimal("6.74357502")),  # circular-exact 0.0355299%; doc: 6.74
        (SEBI_FEE, Decimal("0.018980")),  # doc: 0.02
        (STAMP_DUTY, Decimal("0.2847")),  # doc: 0.28
        (GST, Decimal("8.41726332")),  # doc: 8.42
    ],
)
def test_sec_2_6_line_items(sec_2_6_round_trip: CostBreakdown, component: str, expected: Decimal) -> None:
    assert aggregate_by_name(sec_2_6_round_trip)[component] == expected


def test_sec_2_6_as_a_broker_would_bill_it() -> None:
    # Same round trip with the default (broker-confirmed) whole-rupee STT rounding: STT
    # 14.235 -> Rs 14.00, total Rs 69.46. The doc's Sec 2.6 table does NOT apply this rounding
    # — a real options contract note for this trade would print 24 paise less than the table.
    billed = round_trip_costs(
        entry_date=CURRENT_REGIME_DAY,
        entry_premium=SEC_2_6_PREMIUM,
        exit_date=CURRENT_REGIME_DAY,
        exit_premium=SEC_2_6_PREMIUM,
        quantity=SEC_2_6_QUANTITY,
    )
    assert aggregate_by_name(billed)[STT] == Decimal("14")
    assert billed.total == Decimal("69.46")


def test_sec_2_6_ipft_is_effectively_zero(sec_2_6_round_trip: CostBreakdown) -> None:
    # Rs 0.01 per crore on Rs 18,980 turnover.
    assert aggregate_by_name(sec_2_6_round_trip)[IPFT] == Decimal("0.00001898")


def test_sec_2_6_round_trip_cost_as_a_share_of_premium(sec_2_6_round_trip: CostBreakdown) -> None:
    # Sec 2.6 reports "0.735% of premium = 1.07 premium points". The denominator is the
    # one-way position premium (Rs 9,490), not the two-way turnover -- worth pinning down,
    # because reading it as round-trip turnover halves the apparent hurdle.
    position_premium = SEC_2_6_PREMIUM * SEC_2_6_QUANTITY
    share = sec_2_6_round_trip.total / position_premium * 100
    assert Decimal("0.73") < share < Decimal("0.74")
    points = sec_2_6_round_trip.total / SEC_2_6_QUANTITY
    assert Decimal("1.06") < points < Decimal("1.08")


# ── Regime crossings ─────────────────────────────────────────────────────────────────────


def test_a_trade_before_01_apr_2026_pays_less_stt() -> None:
    # Exact statutory amounts (rupee rounding off) so the 0.10% -> 0.15% ratio is exact.
    before = leg_costs(trade_date=date(2026, 3, 31), side=Side.SELL, premium=146, quantity=65, stt_rupee_rounding=False)
    after = leg_costs(trade_date=date(2026, 4, 1), side=Side.SELL, premium=146, quantity=65, stt_rupee_rounding=False)
    assert after.get(STT) == before.get(STT) * Decimal("1.5")


def test_a_round_trip_can_straddle_a_rate_change() -> None:
    # Overnight positions are out of scope for the strategy, but the API must not assume the
    # two legs share a trade date.
    straddling = round_trip_costs(
        entry_date=date(2026, 2, 27),
        entry_premium=146,
        exit_date=date(2026, 3, 2),
        exit_premium=150,
        quantity=65,
    )
    per_leg_txn = [line.amount for line in straddling.lines if line.name == EXCHANGE_TXN]
    assert len(per_leg_txn) == 2
    assert per_leg_txn[0] == Decimal("146") * 65 * Decimal("0.0003503")
    assert per_leg_txn[1] == Decimal("150") * 65 * Decimal("0.000355299")


def test_short_option_entry_flips_which_leg_pays_what() -> None:
    short_first = round_trip_costs(
        entry_date=CURRENT_REGIME_DAY,
        entry_premium=146,
        exit_date=CURRENT_REGIME_DAY,
        exit_premium=120,
        quantity=65,
        entry_side=Side.SELL,
        stt_rupee_rounding=False,  # exact statutory amount so the rate identity is exact
    )
    totals = aggregate_by_name(short_first)
    # STT on the (higher) entry premium; stamp duty on the (lower) exit premium.
    assert totals[STT] == Decimal("146") * 65 * Decimal("0.0015")
    assert totals[STAMP_DUTY] == Decimal("120") * 65 * STAMP_DUTY_BUY_RATE


# ── Exercise STT and rounding policy ─────────────────────────────────────────────────────


def test_exercise_stt_is_charged_on_intrinsic_value() -> None:
    line = exercise_stt(trade_date=CURRENT_REGIME_DAY, intrinsic_value=Decimal("120"), quantity=65)
    assert line.amount == Decimal("120") * 65 * Decimal("0.0015")
    assert line.name == STT


def test_stt_rupee_rounding_helper() -> None:
    assert stt_rounded_to_rupee(Decimal("14.235")) == Decimal("14")
    assert stt_rounded_to_rupee(Decimal("14.5")) == Decimal("15")
    assert stt_rounded_to_rupee(Decimal("90.90")) == Decimal("91")  # the Jun-2024 note's figure


def test_stt_rupee_rounding_is_the_confirmed_default() -> None:
    # BROKER-CONFIRMED by the Jun-2024 futures note (exact 90.90, billed 91.00). Default ON.
    assert STT_ROUNDS_TO_RUPEE is True
    sell = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    assert sell.get(STT) == Decimal("14")  # exact 14.235, billed 14
    exact = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65, stt_rupee_rounding=False)
    assert exact.get(STT) == Decimal("14.235")


# ── Breakdown plumbing ───────────────────────────────────────────────────────────────────


def test_as_dict_gives_rounded_amounts() -> None:
    breakdown = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    as_dict = breakdown.as_dict()
    assert as_dict[BROKERAGE] == Decimal("20.00")
    assert as_dict[STT] == Decimal("14.00")  # whole-rupee STT (default); 14.24 with it off
    assert all(value.as_tuple().exponent == -2 for value in as_dict.values())


def test_txn_plus_ipft_is_the_bundle_a_note_prints() -> None:
    # Zerodha bills txn + IPFT as one "Exchange transaction charges" line. With the
    # circular-exact 2026 rates the bundle is exactly Rs 3,553 per crore = 0.03553% published.
    breakdown = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    assert breakdown.txn_plus_ipft == (breakdown.get(EXCHANGE_TXN) + breakdown.get(IPFT)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    one_crore = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=Decimal("1000"), quantity=10000)
    assert one_crore.txn_plus_ipft == Decimal("3553.00")


def test_every_line_carries_a_basis_and_a_source() -> None:
    breakdown = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    for line in breakdown.lines:
        assert line.basis.strip()
        assert line.source.strip()


def test_breakdowns_concatenate() -> None:
    one = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65)
    two = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    combined = one + two
    assert len(combined.lines) == len(one.lines) + len(two.lines)
    assert combined.lines == one.lines + two.lines


def test_concatenation_is_exact_on_amounts_but_not_on_rounded_totals() -> None:
    # Concatenation is exact on the *unrounded* amounts... (statutory-exact STT here, so the
    # one-paisa demonstration below is about paisa rounding order, not whole-rupee STT)
    one = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65, stt_rupee_rounding=False)
    two = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65, stt_rupee_rounding=False)
    combined = one + two
    exact = sum((line.amount for line in combined.lines), Decimal("0"))
    assert exact == sum((line.amount for line in one.lines), Decimal("0")) + sum(
        (line.amount for line in two.lines), Decimal("0")
    )

    # ...but *not* on the rounded per-leg totals. Buy leg 27.874629..., sell leg 41.824936...:
    # each rounds down, so the two rounded totals sum to Rs 69.69 while rounding the exact
    # figure once at the end gives Rs 69.70. This is the per-line vs end-of-note rounding
    # question in miniature, and it is why CostBreakdown exposes both totals. Never total a
    # multi-leg trade by adding already-rounded leg totals.
    assert one.total + two.total == Decimal("69.69")
    assert combined.total == Decimal("69.70")


def test_get_raises_for_an_unknown_component() -> None:
    breakdown = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.BUY, premium=146, quantity=65)
    with pytest.raises(KeyError):
        breakdown.get("securities_transaction_levy")


# ── Index futures ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (date(2023, 3, 31), Decimal("0.0001")),  # Finance Act 2013
        (date(2023, 4, 1), Decimal("0.000125")),  # Finance Act 2023; validated by the Jun-2024 note
        (date(2024, 10, 1), Decimal("0.0002")),  # Finance (No. 2) Act 2024
        (date(2026, 4, 1), Decimal("0.0005")),  # Finance Act 2026 / NSE/FATAX/73524
    ],
)
def test_futures_stt_rate_history(on: date, expected: Decimal) -> None:
    assert _rate_at(FUT_STT_SELL_REGIMES, on) == expected


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (date(2023, 3, 31), Decimal("0.0000198")),  # derived: 188 + NSE/FA/56129's Rs 10/crore cut
        (date(2023, 4, 1), Decimal("0.0000188")),  # validated by the Jun-2024 note
        (date(2024, 10, 1), Decimal("0.0000173")),  # NSE/FA/64323 (Rs 173/crore)
        (date(2026, 3, 1), Decimal("0.000018299")),  # NSE/FA/73061 (Rs 182.99/crore)
    ],
)
def test_futures_txn_charge_history(on: date, expected: Decimal) -> None:
    assert _rate_at(FUT_TXN_CHARGE_REGIMES, on) == expected


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (date(2023, 3, 31), Decimal("0.01")),
        (date(2023, 4, 1), Decimal("10")),  # NSE/FA/56129 (futures Rs 10/crore)
        (date(2026, 2, 28), Decimal("10")),
        (date(2026, 3, 1), Decimal("0.01")),  # NSE/FA/73061 rollback
    ],
)
def test_futures_ipft_history(on: date, expected: Decimal) -> None:
    assert _rate_at(FUT_IPFT_PER_CRORE_REGIMES, on) == expected


def test_the_2026_futures_change_is_also_outflow_neutral() -> None:
    # Same event as the options change: +Rs 9.99/crore txn, -Rs 9.99/crore IPFT, bundle
    # unchanged at exactly Rs 183/crore.
    txn_delta = (Decimal("0.000018299") - Decimal("0.0000173")) * Decimal("10000000")
    ipft_delta = Decimal("10") - Decimal("0.01")
    assert txn_delta == ipft_delta == Decimal("9.99")
    bundle = Decimal("0.000018299") * Decimal("10000000") + Decimal("0.01")
    assert bundle == Decimal("183.00")


def test_futures_brokerage_is_capped_at_twenty() -> None:
    # 0.03% of Rs 7.27L is Rs 218.16, so the Rs 20 cap binds at index-futures contract values.
    capped = futures_leg_costs(trade_date=date(2024, 6, 25), side=Side.SELL, price=48480, quantity=15)
    assert capped.get(BROKERAGE) == BROKERAGE_PER_ORDER
    # Below the cap the 0.03% rate applies (never the case for a real index-futures lot, but
    # the min() must point the right way).
    tiny = futures_leg_costs(trade_date=date(2024, 6, 25), side=Side.SELL, price=100, quantity=15)
    assert tiny.get(BROKERAGE) == Decimal("1500") * FUTURES_BROKERAGE_RATE


def test_futures_stt_is_sell_side_only_and_stamp_is_buy_side_only() -> None:
    buy = futures_leg_costs(trade_date=date(2024, 6, 25), side=Side.BUY, price=48480, quantity=15)
    sell = futures_leg_costs(trade_date=date(2024, 6, 25), side=Side.SELL, price=48480, quantity=15)
    assert buy.get(STT) == Decimal("0")
    assert sell.get(STT) > 0
    assert buy.get(STAMP_DUTY) > 0
    assert sell.get(STAMP_DUTY) == Decimal("0")


def test_futures_stamp_duty_is_two_hundred_per_crore() -> None:
    # Futures stamp is 0.002%, LOWER than the 0.003% on options.
    assert STAMP_DUTY_BUY_RATE_FUTURES * Decimal("10000000") == Decimal("200")
    assert STAMP_DUTY_BUY_RATE_FUTURES < STAMP_DUTY_BUY_RATE
    one_crore = futures_leg_costs(trade_date=date(2024, 6, 25), side=Side.BUY, price=Decimal("1000"), quantity=10000)
    assert one_crore.get(STAMP_DUTY) == Decimal("200")


def test_futures_breakdown_shares_the_options_shape() -> None:
    fut = futures_leg_costs(trade_date=date(2024, 6, 25), side=Side.SELL, price=48480, quantity=15)
    opt = leg_costs(trade_date=CURRENT_REGIME_DAY, side=Side.SELL, premium=146, quantity=65)
    assert [line.name for line in fut.lines] == [line.name for line in opt.lines]


# ════════════════════════════════════════════════════════════════════════════════════════
# REAL CONTRACT NOTE FIXTURES — the paisa-exact acceptance gate
# ════════════════════════════════════════════════════════════════════════════════════════
#
# GATE STATUS (updated when the futures note below was added):
#
#   CLOSED — shared machinery. The Jun-2024 BANKNIFTY futures note reproduces to the paisa,
#   which broker-validates everything the options and futures paths share: Decimal paisa
#   arithmetic, per-line itemisation, whole-rupee STT rounding (90.90 -> 91.00), the GST base
#   (brokerage + SEBI + txn + IPFT — the 3.16/3.16 split is only reproducible with SEBI and
#   the bundled txn+IPFT in the base), IPFT-bundled-into-txn-line billing, and date-keying.
#
#   OPEN — options-specific rate values. STT-on-premium %, the 0.0355299% premium txn rate,
#   Rs 50-then-0.01/crore options IPFT and 0.003% options stamp remain circular-sourced, not
#   broker-validated. Drop a real OPTIONS note into REAL_OPTIONS_CONTRACT_NOTES below to close
#   that too; until then test_the_options_note_gate_is_still_open skips loudly.
#
# WHAT A FAILURE MEANS: any mismatch is a real finding, not a test to relax.


@dataclass(frozen=True)
class ContractNote:
    """One real broker contract note, for the paisa-exact acceptance gate.

    ``price`` is the weighted-average traded price per unit (options: premium). Leave a charge
    as ``None`` if the note does not itemise it separately and it will be skipped rather than
    compared against zero. ``txn_plus_ipft`` is the note's single "Exchange transaction
    charges" line (Zerodha bundles IPFT into it). ``net_obligation`` is the pay-in/pay-out
    obligation (futures M2M); ``net_payable`` is the note's bottom line, negative for a debit.
    """

    label: str
    segment: str  # "FUT" or "OPT"
    trade_date: date
    side: Side
    price: Decimal
    quantity: int
    orders: int
    brokerage: Decimal | None = None
    stt: Decimal | None = None
    txn_plus_ipft: Decimal | None = None
    sebi_fee: Decimal | None = None
    stamp_duty: Decimal | None = None
    gst: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    total_levies: Decimal | None = None
    net_obligation: Decimal | None = None
    net_payable: Decimal | None = None


#: Real Zerodha notes. The Jun-2024 BANKNIFTY futures note (supplied by the account holder):
#: SELL 15 (1 lot) BANKNIFTY 24JUN FUT @ WAP 48480.00, closing rate 48478.70, single order,
#: brokerage printed as Rs 1.3333/unit (15 x 1.3333 = 19.9995 -> Rs 20.00 = the flat cap).
#: The exact trade date was not printed on the summary supplied; any date in the
#: 01-Apr-2023..30-Sep-2024 regime window yields identical charges (all four rate tables are
#: constant across it), so a representative date inside the 24JUN contract's life is used.
REAL_CONTRACT_NOTES: list[ContractNote] = [
    ContractNote(
        label="zerodha-jun2024-banknifty-fut-sell-1lot",
        segment="FUT",
        trade_date=date(2024, 6, 25),
        side=Side.SELL,
        price=Decimal("48480.00"),
        quantity=15,
        orders=1,
        brokerage=Decimal("20.00"),
        stt=Decimal("91.00"),  # exact 90.90; billed whole-rupee
        txn_plus_ipft=Decimal("14.40"),  # 13.67136 txn (0.00188%) + 0.7272 IPFT (Rs 10/crore)
        sebi_fee=Decimal("0.73"),
        stamp_duty=Decimal("0.00"),  # sell side; absent from the note
        gst=Decimal("6.32"),
        cgst=Decimal("3.16"),  # "@9% of (Brok, SEBI, Trans & Clearing)" — SEBI is IN the base
        sgst=Decimal("3.16"),
        total_levies=Decimal("132.45"),
        net_obligation=Decimal("19.50"),  # M2M pay-in: (48480.00 - 48478.70) x 15
        net_payable=Decimal("-112.95"),
    ),
]

#: Real OPTIONS notes — still empty; see the gate-status block above.
REAL_OPTIONS_CONTRACT_NOTES: list[ContractNote] = []


def _breakdown_for(note: ContractNote) -> CostBreakdown:
    if note.segment == "FUT":
        return futures_leg_costs(
            trade_date=note.trade_date,
            side=note.side,
            price=note.price,
            quantity=note.quantity,
            orders=note.orders,
        )
    return leg_costs(
        trade_date=note.trade_date,
        side=note.side,
        premium=note.price,
        quantity=note.quantity,
        orders=note.orders,
    )


@pytest.mark.parametrize("note", REAL_CONTRACT_NOTES + REAL_OPTIONS_CONTRACT_NOTES, ids=lambda n: n.label)
def test_contract_note_reproduces_to_the_paisa(note: ContractNote) -> None:
    breakdown = _breakdown_for(note)
    actual = breakdown.as_dict()
    expected = {
        BROKERAGE: note.brokerage,
        STT: note.stt,
        SEBI_FEE: note.sebi_fee,
        STAMP_DUTY: note.stamp_duty,
        GST: note.gst,
    }
    mismatches = {
        name: (want, actual[name]) for name, want in expected.items() if want is not None and want != actual[name]
    }
    if note.txn_plus_ipft is not None and breakdown.txn_plus_ipft != note.txn_plus_ipft:
        mismatches["txn_plus_ipft"] = (note.txn_plus_ipft, breakdown.txn_plus_ipft)
    assert not mismatches, f"{note.label}: expected vs computed {mismatches}"

    if note.cgst is not None or note.sgst is not None:
        half = (breakdown.get(GST) / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert note.cgst is None or note.cgst == half, f"{note.label}: CGST {note.cgst} != {half}"
        assert note.sgst is None or note.sgst == half, f"{note.label}: SGST {note.sgst} != {half}"

    if note.total_levies is not None:
        assert note.total_levies in (breakdown.total, breakdown.total_of_rounded_lines), (
            f"{note.label}: note total {note.total_levies}, computed {breakdown.total} "
            f"(per-line rounding: {breakdown.total_of_rounded_lines})"
        )
    if note.net_payable is not None and note.net_obligation is not None:
        assert (
            note.net_payable == note.net_obligation - breakdown.total
        ), f"{note.label}: net {note.net_payable} != {note.net_obligation} - {breakdown.total}"


def test_the_jun_2024_note_agrees_under_both_rounding_conventions() -> None:
    # For this particular note per-line rounding and end-of-note rounding coincide (both give
    # Rs 132.45), so it cannot discriminate that convention. Recorded so nobody later claims
    # the note settled it.
    note = REAL_CONTRACT_NOTES[0]
    breakdown = _breakdown_for(note)
    assert breakdown.total == breakdown.total_of_rounded_lines == Decimal("132.45")


def test_the_shared_machinery_gate_is_closed() -> None:
    """The Phase 0a contract-note gate, for everything options and futures share, is met."""
    assert REAL_CONTRACT_NOTES, "gate regression: the futures note fixture has been removed"
    assert STT_ROUNDS_TO_RUPEE is True  # broker-confirmed convention stays the default


def test_the_options_note_gate_is_still_open() -> None:
    """Options-specific *rate values* are circular-sourced until a real options note lands."""
    if not REAL_OPTIONS_CONTRACT_NOTES:
        pytest.skip(
            "OPTIONS NOTE GATE STILL OPEN: the shared cost machinery is broker-validated by the "
            "Jun-2024 futures note, but the options-specific rates (STT-on-premium %, 0.0355299% "
            "premium txn charge, options IPFT, 0.003% stamp) are verified against circulars and "
            "the plan doc's worked example only. Add a real Zerodha OPTIONS contract note to "
            "REAL_OPTIONS_CONTRACT_NOTES in tests/test_options_costs.py to close it."
        )
    assert all(n.segment == "OPT" for n in REAL_OPTIONS_CONTRACT_NOTES)
