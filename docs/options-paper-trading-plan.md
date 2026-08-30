# Opening-Hour Index Options Paper Trader — Plan (Rev 2)

**Status:** proposed, not yet implemented. Supersedes the equity-scanner direction for new work.
**Date:** 2026-08-30
**Revision:** Rev 2 — rewritten after adversarial review. Rev 1 (2026-08-23) contained material
errors; every one is listed in §8 rather than silently deleted.

---

## 0. The honest framing

Read this before anything else.

SEBI's *Profitability of Individual Traders in the Equity Derivatives Segment (FY25–FY26)*,
published **20 Aug 2026**, states: **"Sustained profitability remained rare: among traders
active throughout FY22–FY26, only 0.5%"** achieved it. In FY26, **87.7%** of individual
traders lost money net of costs (₹91,685 crore). The loss rate in **options is 87.7% vs 66.0%
in futures**. Profit-makers spent **~22% of gross profits on transaction costs**.

This project is therefore not "build a profitable strategy." It is:

> **Determine, at zero financial risk, whether a 45-minute opening-hour options edge exists —
> and expect the answer to be no.**

A well-built paper trader that returns a confident *no* in six months is a success. The failure
mode is a paper trader that returns a flattering *yes* because it was built with optimistic
fills, a stale chain, or twenty variants ranked on noise. **Every design decision below is
biased toward making a false positive hard.**

---

## 1. Scope

| | |
|---|---|
| **Instruments** | **NIFTY index options — primary.** BANKNIFTY secondary, see §1.2 |
| **Window** | Signal from 09:15. **Entry not before 09:20** (§2.4). Exit by 10:00. |
| **Expiry** | Nearest expiry with **DTE >= 5** calendar days. Never expiry day. |
| **Mode** | **Paper trading only.** No order-placement code path will exist. |
| **Data** | **Licensed broker API only.** NSE scraping is prohibited — see §6. |
| **Deploy** | Single ~$5/1GB VPS, unattended, daily. SQLite, one Python process. |
| **Goal** | "If I had followed this tool, what would my P&L be?" — visible any time. |

Nifty IT was dropped: **it has no listed index options on NSE**. Only NIFTY, BANKNIFTY,
FINNIFTY, MIDCPNIFTY and NIFTYNXT50 have index options.

### 1.1 Contract facts (verified 2026-08-28 against the MII contract master and FAOP73928)

| | NIFTY | BANKNIFTY |
|---|---|---|
| **Lot size** | **65** | **30** |
| **Quantity freeze** | **1,800** | **600** |
| Strike interval | 50 | 100 (monthly), 500 wing |
| Tick size | Rs 0.05 | Rs 0.05 |
| **Weekly expiry** | **Tuesday** | **NONE — discontinued** |
| Monthly expiry | Last Tuesday | Last Tuesday |

Cross-checked: 65 × 24,175 = Rs 15.71 lakh; 30 × 57,496 = Rs 17.25 lakh — both inside SEBI's
Rs 15–20 lakh band. Freeze independently confirmed via contract-master `MaxTradQty` = 1801/601.

> Note: the contract master's `XpryDt` uses a **1980-01-01 epoch, not Unix**. Decoding as Unix
> yields 2016 dates and zero current rows.

### 1.2 Why BANKNIFTY is demoted to secondary

Measured 28-Aug-2026 15:40 from `option-chain-v3`, plus 40 sessions of official bhavcopy:

| | NIFTY weekly | BANKNIFTY monthly |
|---|---|---|
| ATM spread | **0.33 pts / 0.37%** | 4.68 pts / 0.67% |
| ±1–2 strike spread | 0.35 pts / 0.48% | **10.62 pts / 1.37%** |
| DTE available under "DTE>=5" | 5–11 | **5–30** |
| Sessions with worse open dislocation | 90% | **100%** |

**One row of that table needs an honest caveat.** At *exact* ATM, BANKNIFTY monthly (0.67%) is
marginally **narrower in percentage terms** than NIFTY monthly (0.78%) — the like-for-like
comparison, since the NIFTY column above is the weekly. The BANKNIFTY penalty is not at the
money; it appears **one strike out**, where ±2 gives **1.37% vs 0.86%** — 1.6× wider in
percentage and **5.8× in absolute points**, with genuine liquidity holes (56100 CE: zero volume,
2.29% spread). Since strike offset is a backtest parameter (§3.2) and most configs will not sit
exactly ATM, the penalty is the one that binds — but the ATM row should not be quoted as if
BANKNIFTY were uniformly worse.

With that correction, BANKNIFTY is still worse on every axis that matters: no weeklies (so
higher DTE, so less gamma, which is the entire profit engine here), 5.8× the spread one strike
out, no-quote strikes, and open-versus-close pricing dislocation in *every single session
sampled*.

**Decision: build NIFTY first. Add BANKNIFTY only if NIFTY shows signal.** This is also the
single cheapest statistical fix available — see §5.

### 1.3 Expiry resolution (DTE >= 5)

NIFTY weeklies expire **Tuesday**. Rule = "nearest expiry with DTE >= 5":

| Trade day | Next Tue | DTE | Action | Final DTE |
|---|---|---|---|---|
| Mon | +1 | 1 | roll | 8 |
| Tue (expiry) | 0 | 0 | roll | 7 |
| Wed | +6 | 6 | take | 6 |
| Thu | +5 | 5 | take | 5 |
| Fri | +4 | 4 | roll | 11 |

=> NIFTY DTE always lands in **5–11 days**. BANKNIFTY, being monthly-only, lands in **5–30** —
a materially different and worse instrument, not a second sample of the same one.

---

## 2. The governing arithmetic

### 2.1 The move size — square-root-of-time is wrong here, and we measured by how much

Two independent errors in Rev 1's `0.89% × √(45/375) = 0.31%`, pointing in opposite directions.

**Error A — the vol base is too high.** Rev 1 used Varsity's illustrative 0.89% daily SD. At
India VIX 10.68 (28 Aug 2026 close) the daily SD is **0.673%** — Rev 1 is ~33% high.

**Error B — √t understates the opening window.** Realised variance from NIFTY 50 five-minute
bars, 59 sessions (8 Jun – 28 Aug 2026), equal-weighted by day, overnight gap excluded:

| Window | Share of session RV | Uniform (√t) benchmark | Ratio |
|---|---|---|---|
| 09:15–09:20 | 2.92% | 1.33% | **2.19×** |
| First 15 min | 7.79% | 4.0% | 1.95× |
| First 30 min | 13.94% | 8.0% | 1.74× |
| **First 45 min** | **18.85%** | **12.0%** | **1.57×** |

Independently corroborated at **18.84%** by Singh & Gangwar, MPRA Paper 89689, from 1-minute
NIFTY *futures* 2011–2018 — different instrument, different frequency, sample 8–15 years
earlier, agreeing to two decimal places. The Indian intraday shape is **reverse-J, not U**:
front-loaded volatility with a weak close.

So the correct scaling factor is **√0.1885 = 0.434**, not `√(45/375) = 0.346`.

**The two errors nearly cancel in the headline number and nowhere else.**
`0.673% × 0.434 = 0.292%` against Rev 1's stated 0.31%. Rev 1's governing figure was
approximately right *by accident*; **every quantity derived from the 0.89% base or the 0.346
factor separately is wrong** — including the §3.6 stop distance, which is ~25% too tight.

**Correct formula. Derive from live India VIX daily as a runtime input, never a constant:**

```
daily 1SD  = VIX / sqrt(252)                    (%)      # 252 trading days, per Varsity
45-min 1SD = daily 1SD * 0.434                  (%)      # empirical, NOT sqrt(45/385)
```

| India VIX | daily 1 SD | 45-min 1 SD | @ NIFTY 24,175 |
|---|---|---|---|
| **10.68** (28 Aug 2026) | **0.673%** | **0.292%** | **70.6 pts** |
| 12.00 | 0.756% | 0.328% | 79.3 pts |
| 13.50 | 0.850% | 0.369% | 89.2 pts |
| 15.00 | 0.945% | 0.410% | 99.1 pts |
| 20.00 | 1.260% | 0.547% | 132.2 pts |

52-week VIX range is 8.86–28.91, so regime dependence spans a factor of 3. It must be a
variable, and the 0.434 factor must be re-estimated periodically from our own bar data.

> Note: the session is now **385 minutes**, not 375 — NSE moved the close to **15:40 effective
> 03-Aug-2026** (a Closing Auction Session, **equity derivatives only**; the cash segment still
> closes 15:30 — matters when comparing option bars against index bars after 15:30), confirmed
> by a live `records.timestamp` of "28-Aug-2026 15:40:00". Any
> surviving `/375` denominator is stale. The 0.434 factor is measured, so it is unaffected.

### 2.2 Theta is small but not zero

NIFTY DTE-7 ATM theta = **−10.42 pts/day** => **1.25 pts** over 45 minutes of trading time
(0.33 pts of calendar decay). DTE-5 = −12.33/day. Rev 1's "~0.6 points" understated it 2×.

The reference signal used throughout this document: at VIX 10.68 a 1-SD move is 70.6 spot
points, so an ATM option (δ ≈ 0.50) gains **~35.3 premium points** = Rs 2,294 per 65-lot.

At 1.25 pts against a 35.3 pt signal, theta is **~3.5%** of it. **Small. Not "dead."** No
strategy can profit *from* it in this window, but it is a real drag of roughly the same size as
one round trip of tax.

### 2.3 Vega dominates — this is the finding that reshapes the strategy list

| | NIFTY DTE 7 | BANKNIFTY DTE 7 | BANKNIFTY DTE 30 |
|---|---|---|---|
| ATM vega (pts per IV pt) | **13.26** | 31.77 | 65.75 |
| 1-SD delta gain @ VIX 10.68 | 35.3 pts | — | — |
| **IV drop that erases it** | **2.7 pts** | — | — |

**A 2.7-point IV drop cancels an entire favourable 1-SD move.** And §3.2 establishes that 09:15
is the daily IV *maximum* — Varsity's own Infosys case shows IV collapsing 40.26% → 28% within
three minutes of the open.

Rev 1 identified this hazard in §3.2 and then built 8 of its 10 configs as naked long options
pointed straight into it. That is the plan's worst internal contradiction.

**Design consequence:** vega-neutral structures are not one option among several. They are the
structurally correct answer for a 09:15 entry, and the burden of proof is on naked longs.

### 2.4 The open is hostile — measured, not assumed

Own computation, 40 sessions of official NSE F&O bhavcopy through 2026-08-28. Put-call parity
violation `|C - P + K - F|` as % of futures price, ATM±5, same-expiry matched:

| | NIFTY | BANKNIFTY |
|---|---|---|
| Median dislocation at **OPEN** | **0.0569%** (~13.8 pts) | **0.0850%** (~49 pts) |
| Median at **CLOSE** | 0.0088% (~2.1 pts) | 0.0126% (~7.3 pts) |
| Median ratio | **6.75×** | **6.81×** |
| Sessions worse at open | 90% (36/40) | **100% (40/40)** |

*Caveat, stated because it matters:* `OpnPric` is each contract's first trade, and CE/PE/futures
first trades are unsynchronised — that asynchrony is part of the real effect but inflates the
magnitude. F&O `ClsPric` is a half-hour weighted average, which smooths the close. **Treat the
ratio as an upper bound; treat the direction and the 90–100% consistency as robust.**

**Design consequence: no entry before 09:20.** Rev 1 had configs entering at 09:15 and 09:20.
The 09:15 entries are removed.

### 2.5 There is no market-maker backstop, and no market orders

A keyword scan of the **full 152,771-character** current NSE F&O Consolidated Circular
(FAOP73928) returns **zero** occurrences of `impact`, `market maker`, and `liquidity`, against
12 control hits for `eligibility criteria`.

- **No market-maker quoting obligations exist in NSE index options.** Not suspended at the
  open — nonexistent at all times.
- **No impact-cost metric exists for index options.** It is a cash-market-only measure at NSE.

From the same circular, verbatim:

> *"'Market' price orders shall not be allowed in a contract which has not traded for the day
> i.e. LTP is not available for the day. Market orders received in such scenario shall be
> rejected by the Exchange…"*
> *"Stop Loss orders with 'Market' price condition (SL-M) for Index Options and Stock Options
> contracts are not allowed."*
> *"Market Price Protection (MPP) applicable only for index futures contracts"*

**At 09:15:00 no option has an LTP for the day, so every market order is rejected.** SL-M is
banned in options outright. MPP does not cover options.

Options also have **no pre-open auction**. NSE/FAOP/74970 (1 Jul 2026), FAQ Q5, verbatim:
*"Pre-open shall not be applicable in following scenarios: 1. Spread & Option contracts on
Indices and stocks."* Futures got a pre-open (revised 09:00–09:15, effective 07-Sep-2026);
options open cold. The opening price band is a **Black-Scholes synthetic** derived from the
cash pre-open price and MIBOR (±40% for premium > Rs 50; ±Rs 20 below).

**Design consequence:** the simulator must model **limit orders only**, must allow an entry
attempt to **fail** (no quote / not marketable), and cannot use SL-M for the stop or the 10:00
square-off. Rev 1 assumed all three were available.

### 2.6 The cost stack (STT resolved)

Source: **NSE circular NSE/FATAX/73524 (Ref 02/2026), dated 31 March 2026**, implementing the
Finance Act 2026, **effective 1 April 2026**:

- Sale of an option: **0.10% → 0.15%** of premium
- Sale of an exercised option: 0.125% → **0.15%** of intrinsic
- Sale of a futures contract: 0.02% → **0.05%** (relevant only if a synthetic is ever built
  with a futures leg)

This was the last genuinely unresolved number in Rev 1. `costs.py` must key STT by trade date
across three regimes (0.0625% → 0.10% from 1 Oct 2024 → 0.15% from 1 Apr 2026), because the
backtest window straddles the boundaries.

Round trip, 1 lot ATM NIFTY, 146 pts premium × 65. **Valid for trade dates from 2026-03-01
only** — the 0.03553% txn rate and Rs 0.01/crore IPFT arrived together in NSE/FA/73061 as one
revenue-neutral change; between 2024-10-01 and 2026-02-28 the pair was 0.03503% + Rs 50/crore
(where IPFT is no longer negligible and Zerodha bills GST on it too):

| Component | Rate | Amount |
|---|---|---|
| Brokerage | Rs 20 × 2 | Rs 40.00 |
| STT | 0.15% sell premium | Rs 14.24 |
| NSE txn charges | 0.03553% premium | Rs 6.74 |
| SEBI | Rs 10/crore | Rs 0.02 |
| IPFT | Rs 0.01/crore | Rs 0.00 (0.00002) |
| Stamp duty | 0.003% buy side | Rs 0.28 |
| GST | 18% of (brokerage+SEBI+txn+IPFT) | Rs 8.42 |
| **Total** | | **Rs 69.70** |

(Rev 2.0 of this table said Rs 69.71 with STT 14.23 and booked the IPFT *rate* as an *amount* —
three arithmetic slips caught when `costs.py` was built against it. Exact total 69.69956;
summing per-line rounded figures gives 69.69, so the engine exposes both `total` and
`total_of_rounded_lines`. Further, a real Jun-2024 futures contract note proved **STT is
statutorily rounded to the whole rupee** (90.90 billed as 91.00), so a broker would bill this
example's STT as Rs 14.00 and the total as **Rs 69.46** — the table above shows unrounded model
values; `costs.py` defaults to broker billing. Pinned in `test_sec_2_6_as_a_broker_would_bill_it`.)

= **0.735% of one-way premium** (Rs 9,490 = 146 × 65; against round-trip turnover it is half
that, ~0.37% — quote the denominator or the hurdle silently doubles/halves)
= **1.07 premium points = 2.14 points of spot move.**

Adding spread, against the §2.2 reference signal of 35.3 premium points = Rs 2,294 per lot:

| Spread assumption | All-in cost | % of a 1-SD win |
|---|---|---|
| 0 (taxes and brokerage only) | Rs 70 | 3.0% |
| 0.5 pt (measured mid-session ATM) | Rs 102 | 4.5% |
| 1 pt | Rs 135 | 5.9% |
| **2 pt (open, ~6× mid-session)** | **Rs 200** | **8.7%** |
| 3 pt | Rs 265 | 11.5% |
| 5 pt | Rs 395 | 17.2% |

Two-leg synthetic doubles brokerage to Rs 80 and pays STT on both the short leg's sell at entry
and the long leg's sell at exit: **Rs 269 at 1 pt/leg, Rs 399 at 2 pt/leg** — 2–3× the single
leg. **Vega neutrality is not free; whether it pays for itself is an empirical question, not an
assumption.**

**Rev 1's loophole #1 claimed costs "can flip a gross-profitable strategy firmly negative."
That was overstated.** Costs are ~4–10% of a 1-SD move — a real hurdle, not a wall. Re-ranked
in §6. (SEBI's own figure: profit-makers spend ~22% of gross profits on costs.)

### 2.7 Staleness is a first-order error term

Using the **measured** opening shape from §2.1 rather than √t — the first five minutes carry
2.92% of session variance — 5 minutes of chain staleness at 09:15 is a 1-SD drift of
`0.673% × √0.0292 = 0.115%` = **27.8 NIFTY points = 13.9 premium points = 39% of the entire
1-SD signal, as pure timing noise.**

That is not a rounding error; it is the same order as the edge being hunted. NSE publishes no
refresh SLA for `option-chain-v3`; the payload carries only a `records.timestamp`.

**Design consequence:** the engine must record the feed timestamp on every decision and refuse
to act on a quote older than a configured threshold (default 60s). Staleness must appear as a
column in results, not be silently absorbed.

---

## 3. Strategy library

### 3.1 Structures

| Structure | Verdict |
|---|---|
| **Synthetic Long / Short** (long ATM CE + short ATM PE, or reverse) | **Primary.** The only theta- *and* vega-neutral structure. Delta ~1.0. Immune to the §2.3 IV crush. Cost: 2 legs. |
| **Long Call / Long Put** | **Secondary, as the vega-exposed control.** Cheapest to execute; directly exposed to the crush. Their whole purpose is to measure whether vega neutrality is worth 2× the cost. |
| Long Straddle | **Out.** Maximum vega long at the daily IV maximum. §2.3 makes this indefensible. |

Everything else remains out for the Rev 1 reasons, which survive review: multi-day theta engine,
or an expiry breakeven 2–7.5% away against a 0.233% 1-SD window. Explicitly out: Iron Condor,
short straddle/strangle, long strangle, both credit spreads, all ratio/ladder spreads, naked
short call/put, PCP arbitrage, futures calendar.

Bull Call / Bear Put spreads: Rev 1 called them "strictly dominated" on net delta ~0.28 vs 0.50.
That reasoning used the same broken delta model as §3.2 below and **should be treated as
unproven** — but they stay out on cost grounds (2 legs, no vega benefit).

### 3.2 Strike selection — Rev 1 was wrong, and the conclusion may invert

**Rev 1 §3.1 claimed 2–3 strikes OTM has delta ~0.10–0.15 and gains "~7–11 pts, inside the
spread". Both halves are wrong.**

Black-Scholes at NIFTY 24,000, IV 11%, 50-pt strikes:

| Strike | DTE 5 δ | DTE 7 δ | DTE 11 δ | DTE-7 premium | Gain on 1 SD, as % of premium |
|---|---|---|---|---|---|
| ATM | 0.503 | 0.503 | 0.504 | 145.85 | 27.7% |
| 3 OTM | 0.317 | **0.344** | 0.376 | 83.38 | **34.0%** |
| 5 OTM | — | 0.251 | — | 54.28 | 38.8% |
| 10 OTM | — | 0.089 | — | 14.99 | 52.4% |

Why the error: at 11% IV and 7 DTE the **option-life** 1-SD is ~366 points, so 3 strikes
(150 pts) is only **0.41 SD** out — nowhere near the tail Rev 1 imagined. And a 3-OTM option
gaining ~28 points is nowhere near the 0.33–0.55 pt measured spread.

**The override of Varsity Ch 22 is withdrawn.** Return-on-capital *rises* monotonically with
OTM-ness. Varsity's "same day → 2–3 strikes OTM" advice may well be right.

**Rule: do not hard-code a strike. Make strike offset a first-class backtest parameter
{ATM, +1, +2, +3} and let the data decide.** Constrain only by measured liquidity: reject any
strike whose quoted spread exceeds a configured % of premium at decision time. Note the
countervailing force — % gain rises with OTM-ness, but so does spread as % of premium
(NIFTY weekly: 0.37% ATM → 0.91% at ±3–10 → 6.52% at ±11–30). The optimum is empirical.

### 3.3 Why 09:15 is hostile to long volatility

**09:15 is the daily IV maximum, not the minimum.** Varsity's Infosys case documents IV
collapsing **40.26% → 28% within three minutes of the open**. Combined with §2.3's vega
figures, a long-vol entry at the open is adversely selected on the dominant Greek.

Short-vol has a real intraday engine here — but it is a **vega** trade, not theta. If ever
built it must be **defined-tail**, never naked: at DTE 5–11 an ATM short is maximum short gamma
into the most violent 45 minutes of the session, with §2.5's no-market-maker finding meaning
there is no guaranteed exit quote.

### 3.4 Provenance of the entry signals — corrected

An exhaustive grep of all 149 core Varsity chapters **plus all 604 Innerworth chapters** found
**zero** content on the pre-open, first-hour volatility, opening-range breakouts, or gap
trading. Varsity's only prescribed intraday entry is **3:20 PM**; it states *"closing is more
important than the opening."* That part of Rev 1 stands.

**But Rev 1's claim that "the opening-hour timing thesis is ours" was an overclaim.** Published
work exists: Zarattini & Aziz (SSRN 4416622, 2023) and Zarattini, Barbon & Aziz (2024). Three
things about it must be recorded, because they cut against us:

1. **It is not actually a breakout strategy.** Verbatim: *"if during the first 5 minutes the
   market moved up, we took a bullish position starting from the second candle's opening
   price."* That is first-candle-direction momentum, not a range breakout. Confirmed by an
   independent reimplementation (`giovannibrusco/zarattini-2023-orb-qqq`).
2. **The base result is worse than buy-and-hold.** ORB across all US stocks 2016–2023: 29%
   total, **Sharpe 0.48** — against S&P 500's 198%, Sharpe 0.78. *All* headline performance
   comes from a relative-volume "Stocks in Play" top-20 overlay selected and evaluated
   **in-sample, with no walk-forward or out-of-sample validation**. The 30-minute variant
   returns Sharpe 0.21.
3. **The authors are not disinterested.** Zarattini runs Concretum Research, which sells
   strategy subscriptions; Aziz runs Bear Bull Traders. Both papers are marketed on Concretum's
   own site.

**The peer-reviewed evidence is thinner still, and it is not about equities.** The only
peer-reviewed ORB result found is Holmberg, Lönnbark & Lundström, *"Assessing the profitability
of intraday opening range breakout strategies"*, **Finance Research Letters 10(1):27–33 (2013)**
— run on **US crude oil futures**, not equities and not options. Its own sub-period analysis is
damning: sub-period 1 (1983–92) is **insignificant, p = 0.12–0.25**, and the authors write that
the result is *"not robust to time and to a large extent explained by the most recent (and most
volatile) period."* Costs are a flat 0.08% assumption and there are no stops.

**The only Indian study of this anywhere returns a null.** Wang & Gangwar (SSRN 5198458) test
opening-range breakouts on NSE and report **bootstrap p-values of 0.45–0.50 — not significant at
any conventional level**. Flagged honestly: the PDF could not be retrieved (SSRN returned 403),
so this rests on the abstract and citing sources, not a read of the methodology.

**Honest statement for the docs and UI: Varsity supplies the pricing machinery (Greeks, √t
ranges, ATR stops, delta-as-probability). The opening-hour timing thesis is not Varsity's. The
nearest published support is methodologically weak, on US equities, and vendor-authored; the
only peer-reviewed version is on crude oil and explicitly unstable across sub-periods; and the
only Indian test returns bootstrap p ≈ 0.5. We are not standing on a literature. We are testing
a hypothesis the literature has so far failed to confirm.**

### 3.5 The configurations — cut from 20 to 6

This is the single most important change in Rev 2. See §5 for why.

All share: entry no earlier than 09:20, limit orders only, hard exit by 10:00, vol-based stop
sized off live VIX.

| # | Name | Structure | Entry trigger | Strike |
|---|---|---|---|---|
| 1 | `orb_synth` | Synthetic Long/Short | Break of 09:15–09:30 range, direction of break | ATM |
| 2 | `orb_naked` | Long Call / Long Put | Same trigger as #1 | parameterised |
| 3 | `gap_cont_synth` | Synthetic Long/Short | Gap > ±0.3%, enter 09:20, trade with the gap | ATM |
| 4 | `gap_fade_synth` | Synthetic Long/Short | Gap > ±0.5%, trade against the gap | ATM |
| 5 | `mom_synth` | Synthetic Long/Short | First 10-min return > ±0.2% | ATM |
| 6 | `mom_naked` | Long Call / Long Put | Same trigger as #5 | parameterised |

**NIFTY only at first pass => 6 variants, not 20.** Long/short are one config with a sign, not
two configs. #2 and #6 are the deliberate vega-exposed controls against #1 and #5.

Dropped from Rev 1: `orb_call_otm1` (subsumed into #2's strike parameter), `vwap_reclaim_call`
(no prior, purely additive to the multiple-comparisons burden), and the `iv_crush_condor`
(short gamma with no market-maker backstop per §2.5 — it can be revisited only after the
liquidity model is validated against real fills).

### 3.6 Exits

Three, whichever fires first. **All must be expressible as limit orders** (§2.5):

1. **Vol-based stop**, ported from Varsity Ch 18, with **both** inputs corrected:
   `SL distance = daily vol × 0.434`, where daily vol comes from live India VIX (§2.1) and
   **0.434 is the measured opening-window factor, not √(45/385) = 0.342**. Rev 1's 0.346 makes
   the stop **~25% too tight in SD terms**, which mechanically inflates the stop-out rate.
   Use **ATR** as the gap-aware vol input (Varsity: a plain high-low range "would be ignoring
   the gap up and gap down openings"). Varsity's warning applies verbatim — a fixed-percentage
   stop sits "well within the noise levels." **SL-M is illegal in options**, so this is a
   stop-limit and the simulator must model the case where it does not fill.
2. **Target** at a configurable multiple of the SL distance (default 1.5R).

   **Horizon mismatch — sized deliberately.** A config triggering on the 09:15–09:30 range
   enters ~09:32, leaving 28 minutes, not 45. Stop and target must be scaled to the *residual*
   window, not the full one, or the trade times out before either level is reachable. Rev 1
   sized every exit to 45 minutes regardless of entry time; Monte Carlo on that specification
   put ORB/VWAP timeout rates at **78–82%**, meaning four trades in five would have been
   decided by the clock rather than by the thesis. `strategies.py` must compute exit distances
   from `10:00 − entry_time`, and **timeout rate is a reported metric**, not a footnote.
3. **Hard time stop at 10:00** — Varsity-sanctioned (the RBI case study describes a *"predefined
   time based stoploss"*). Modelled as a marketable limit at the far touch, **with an explicit
   failure branch** if no quote exists.

---

## 4. Architecture

One process, one file-backed DB.

```
app/options/
  calendar.py    ~60 LOC   trading days + NSE holidays (hardcoded from NSE circulars — jugaad-data dropped, see §7), DTE>=5 expiry resolver
  broker.py     ~120 LOC   LICENSED feed adapter (Kite and/or Dhan) - live chain snapshots
  backfill.py   ~100 LOC   Dhan expired-options puller, IF Phase 0 validates it (§5.1)
  contracts.py   ~50 LOC   lot sizes, freeze limits, strike steps, tick size
  costs.py       ~50 LOC   Indian cost stack - unit-tested against a real contract note
  liquidity.py   ~70 LOC   NEW. spread/quote-presence gate, staleness gate, fill model
  position.py    ~80 LOC   multi-leg position + per-leg mark-to-market. SHARED.
  strategies.py ~120 LOC   the 6 configs as declarative specs + trigger fns
  engine.py     ~140 LOC   the replay/decision loop. SHARED by backtest and paper.
  backtest.py    ~60 LOC   drives engine over historical bars
  paper.py       ~90 LOC   drives engine over live snapshots, daily 09:15-10:00
  metrics.py     ~90 LOC   win rate, expectancy, max DD, per-day P&L, DEFLATED SHARPE
  web.py         ~80 LOC   dashboard routes + one Jinja2 page
```

**~1,110 LOC.** Two design rules, both load-bearing:

> **1. `engine.py`, `position.py`, `strategies.py`, `costs.py` and `liquidity.py` are shared
> byte-for-byte between backtest and paper trading.** Only the bar source differs. This is the
> single best defence against backtest-vs-live divergence.
>
> **2. `liquidity.py` is not optional and not a stub.** Every fill goes through it. It owns the
> §2.4 open-dislocation penalty, the §2.5 no-quote failure branch, and the §2.7 staleness gate.
> A backtest that bypasses it is invalid by construction, so there is no code path that can.

`liquidity.py` is new in Rev 2 and is the direct answer to the finding that there are no market
makers, no impact-cost metric, no market orders at 09:15, and 6.75× pricing dislocation at the
open. Rev 1 handled all of this with one line ("fill buys at ask, sells at bid").

### 4.1 Stack

| | Choice | Note |
|---|---|---|
| DB | **SQLite** via `aiosqlite` | already a dev dep; no Postgres, no Redis |
| Scheduler | plain `asyncio` loop in FastAPI lifespan | matches repo pattern; no APScheduler |
| UI | **one Jinja2 page** served by FastAPI | no node, no build step, no nginx |
| Auth | **broker API token** | see §6 — this is now required, not avoidable |
| New deps | `jinja2`, `aiosqlite`, `jugaad-data`, `py_vollib` | py_vollib now needed for §2.3 vega |

### 4.2 Data sources — completely revised

| Purpose | Source | Auth | Cost | Status |
|---|---|---|---|---|
| **Live paper** | **Kite Connect** (account already held) or Dhan | token | Rs 500/mo | **Required** |
| **Backtest** | Dhan expired-options | token | Rs 499/mo | **Blocked on §5.1** |
| Holidays / expiry | Hardcoded from NSE circulars (2024–26) in `calendar.py` | none | free | Done in Phase 0a; `jugaad-data` dropped (non-OSI `LICENSE.YOLO.md`, and a live dep for a static list is a needless failure mode) |
| EOD cross-check | **official NSE F&O bhavcopy** | none | free | OK, per-strike OHLC |

**Rev 1's plan to scrape NSE `option-chain-v3` for the live feed is withdrawn. See §6.**

**On Kite, correcting Rev 1.** Rev 1 dismissed Kite with *"would buy nothing for this."* That
was wrong. Two facts, both true:

- Zerodha support, verbatim: *"You cannot access historical data for expired options contracts
  on Kite."* The `continuous` flag covers NFO/MCX **futures** only, **day** candles. Root cause:
  exchanges flush and reuse `instrument_token` at every expiry. **This verdict stands** — Kite
  cannot do the backtest.
- But Kite **can** do the live feed, licensed and contractually permitted, from a datacentre IP.
  That is precisely the job NSE scraping cannot legally or technically perform. **Also note: a
  Zerodha trading account does not itself confer API access — Kite Connect is a separate
  Rs 500/mo subscription.**

Kite's daily token/TOTP login remains a real operational problem for an unattended VPS
(Rev 1 loophole #5). It is no longer avoidable, only manageable — see §6 loophole #5.

---

## 5. Statistical validity — new section, and the reason for §3.5

Rev 1 proposed **20 tracked variants** and a "top 10" ranking. Under a **pure zero edge**, the
expected maximum t-statistic across N independent variants is:

| N variants | E[max t] | Implied annualised Sharpe (2.5 yr @ 250 trades/yr) |
|---|---|---|
| 6 | ~1.35 | ~0.85 |
| 10 | 1.54 | ~0.97 |
| **20** | **1.86** | **1.18** |
| 40 | 2.16 | 1.37 |
| 243 (realistic knob-twiddling) | 2.80 | ~1.9 |

**A backtest Sharpe of ~1.2 from the best of 20 variants is exactly the null expectation.** Rev 1
would have produced a flattering leaderboard from pure noise and had no mechanism to detect it.
This is the single most likely way this project produces a wrong answer.

Six mandatory controls:

1. **Pre-register the 6 configs** (§3.5) in git before any backtest runs. The commit hash is the
   registration record. Adding a 7th config after seeing results resets the clock.
2. **Report deflated Sharpe**, adjusted for the number of trials actually run — not raw Sharpe.
   `metrics.py` owns this and must count trials, including abandoned ones.
3. **Walk-forward, never single-pass.** Parameters fit on window *k* are evaluated only on
   window *k+1*.
4. **Hold out the most recent 6 months untouched** until the configs are frozen. Look once.
5. **Report gross and net side by side**, always, so cost sensitivity is never hidden.
6. **Forward paper trading is the real test.** The backtest is a **negative filter only** — its
   job is to eliminate clearly-bad configs, never to certify a good one.

**A config must clear an economic bar, not just a statistical one:** net expectancy after costs
must exceed the §2.6 cost hurdle by a margin that survives the §2.4 open-dislocation penalty.
Statistical significance on gross P&L is not a result.

### 5.1 Phase 0 — blocking validations

Nothing else starts until these are answered. Every one can invalidate design.

1. **[FATAL RISK] Validate Dhan's relative-strike keying.** Dhan docs, verbatim: *"Expired
   options data is stored on a minute level, based on strike price relative to spot (example
   ATM, ATM+1, ATM-1, etc.)"*. Because the key is **relative to spot** and spot moves intraday,
   the "ATM" series may silently switch contracts mid-session — which would make it impossible
   to reconstruct a fixed-strike 45-minute P&L path, and would break the shared-engine rule,
   since the live broker feed is keyed by **absolute** strike.
   **Test:** pull one day, find a minute where spot crosses a strike boundary, check whether the
   "ATM" premium series jumps discontinuously.
   **If it fails:** Dhan is unusable for this. Fallbacks, in order — (a) check whether Dhan
   exposes absolute strikes anywhere; (b) find another licensed vendor of expired intraday
   options; (c) **drop the backtest entirely and go straight to forward paper trading.** (c) is
   slower but not fatal — §5 already says the backtest cannot certify anything.
2. **Confirm live-feed viability from the VPS.** Verify the Linode region of `172.105.40.8`, and
   confirm the chosen broker API serves it. Measure the real refresh cadence and the observed
   quote latency against the §2.7 60s gate.
3. **Verify the cost stack against a real Zerodha options contract note.** You can supply this —
   it is the only Phase 0 item requiring your input.
4. **Measure spreads live in the 09:15–09:30 window** for 10 sessions before writing a strategy.
   **No published bid-ask data exists for that window in any primary source** — the §2.4 PCP
   measurement is our own proxy and an upper bound. This must be measured, not modelled.
5. **VPS housekeeping:** 53 pending updates, pending reboot, and total RAM unknown (the banner
   reported only a percentage).
6. **Re-estimate the 0.434 opening-window factor from our own bar data, and keep re-estimating
   it.** The value is empirical (§2.1), corroborated across two independent studies, but it is
   a *regime* property, not a constant — the reverse-J flattens in calm regimes and steepens in
   stressed ones. `metrics.py` recomputes realised variance share of the 09:15–10:00 window each
   quarter from our own captured bars and **flags a drift of more than ±0.05**, because the stop
   sizing in §3.6 depends on it directly. A hard-coded 0.434 that silently goes stale is the
   same class of error as Rev 1's hard-coded 0.346.

*Already answered since Rev 1: BANKNIFTY cadence (monthly-only), lot sizes (65/30), freeze
limits (1,800/600), STT (0.15%), `option-chain-v3` field names (`bidprice`/`askPrice` are
genuine best bid/ask — note the inconsistent casing).*

### 5.2 Statistical power — the experiment can only detect a large edge

This section was written while sequencing §10 and it changes what the project can honestly
promise. §5 asks "how do we avoid a false positive." This asks the opposite question: **given
the sample size available, what is the smallest real edge we could ever detect?** The answer is
uncomfortable.

For a strategy with annualised Sharpe `S` trading `n` times a year, per-trade Sharpe is
`S / √n`, and the t-statistic after `N` trades is `(S / √n) × √N`. At the conventional `t = 2`:

| True annualised Sharpe | Trades needed for t = 2 | Years at ~125 trades/yr |
|---|---|---|
| 0.5 | 4,000 | **32** |
| 1.0 | 1,000 | **8** |
| 1.5 | 444 | **3.6** |
| 2.0 | 250 | **2** |

Now invert it against what we will actually have:

| Sample | Trades | Smallest detectable annualised Sharpe |
|---|---|---|
| **6 months forward paper** | ~60 | **4.08** |
| 5-year backtest | ~625 | **1.27** |
| 5-year backtest, deflated for 6 configs | ~625 | **~1.52** |

Three consequences, all load-bearing:

1. **Six months of forward paper trading cannot confirm an edge.** It would take a Sharpe above
   4 — implausible in the most liquid index option in the world — to clear t = 2 on 60 trades.
   Forward paper trading's real jobs are (a) validating that the infrastructure, fills and cost
   model match reality, and (b) rejecting a *large negative* expectancy, which is detectable
   fast because costs alone impose a reliable drift.
2. **All the statistical power lives in the backtest.** This promotes Phase 0 item 1 (Dhan's
   relative-strike keying) from "blocks a nice-to-have" to **"blocks the only route to an
   answer."** If no vendor of expired intraday options data works out, the project cannot
   produce a statistically meaningful verdict at all — only an infrastructure result. That must
   be said out loud before any money is spent on subscriptions.
3. **Anything that clears the bar should be assumed to be a bug.** If a 45-minute NIFTY window
   shows Sharpe 1.5+, the correct first hypothesis is lookahead, survivorship in the strike
   series, or a fill model that is too kind — not an edge. §5's controls exist to make that
   check reflexive rather than optional.

**This does not kill the project. It renames the deliverable**: from "find the top strategies"
to "build an instrument honest enough that its *negative* result can be trusted, and that would
catch a large edge if one existed." That is still worth six months, and it is still free.

---

## 6. Compliance — the finding that reshaped the architecture

**NSE's website Terms of Use prohibit, verbatim, use of the site's data for:**

> **"virtual trading or simulation activities"**

They separately prohibit scraping and automated access. **A paper-trading system fed by scraped
NSE option-chain data violates the ToU on two independent grounds** — automated access *and*
the simulation prohibition. Rev 1 cited "Auth: none needed" as an advantage. Unauthenticated is
not licensed.

NSE further reserves the right to treat unlicensed redistribution — **even free of charge** — as
illegal data vending, to investigate, to take legal action, and to terminate access. Governed by
Indian law.

**The compliant path is licensed broker data with a data agreement.** That is why §4.2 now
requires a paid broker feed. This is not a cost optimisation we lost; it is the difference
between a project you can run and one you cannot.

Independently, NSE **blocks datacentre IPs** and rate-limits to ~3–4 req/min per IP. Users on
PythonAnywhere hit exactly this on the option-chain endpoint; PythonAnywhere staff, verbatim:
*"It's possible that nseindia.com block access from our machines. It may be based on IP address
or country, but there is not really anything that we can do about it."* 403s persist until
request characteristics change — waiting does not clear them. So the free path was likely
technically dead on the target host as well as legally barred.

`wss://streamer.nseindia.com/streams/fo/mbp` exists and returns HTTP 101, but unauthenticated
usability is **not established** and it is subject to the same ToU. **Do not design against it.**

Free NSE data remains fine for the uses that are neither automated-at-scale nor simulation:
holiday calendars, expiry ladders, and the **official published bhavcopy** for EOD cross-checks.

---

## 7. Loopholes, re-ranked

| # | Loophole | Handling |
|---|---|---|
| 1 | **NSE ToU prohibits scraping AND "virtual trading or simulation activities".** Kills the free live feed. | §6. Licensed broker feed only. Architecture changed. |
| 2 | **NSE blocks datacentre IPs; ~3-4 req/min.** VPS may never have worked. | §6. Broker API. Phase 0 item 2 verifies from the actual host. |
| 3 | **Dhan keys expired data by strike RELATIVE TO SPOT.** May make fixed-strike 45-min reconstruction impossible. | Phase 0 item 1. Explicit fallback ladder ending in "no backtest". |
| 4 | **20 variants manufacture Sharpe ~1.18 from noise.** | §5. Cut to 6, pre-registered, deflated Sharpe, walk-forward, held-out 6 months. |
| 5 | **Vega dominates; 3 IV pts cancels a 1-SD move; 09:15 is peak IV.** | §2.3. Vega-neutral synthetics promoted to primary; naked longs kept only as controls. |
| 6 | **No market makers exist. Market orders rejected at 09:15. SL-M banned. MPP excludes options.** | §2.5. `liquidity.py` models no-quote failure; limit orders only; entry >= 09:20. |
| 7 | **Open dislocation 6.75x normal, 90-100% of sessions.** | §2.4. Entry delayed to 09:20; open penalty in the fill model; Phase 0 item 4 measures it live. |
| 8 | **Daily broker token expiry breaks unattended operation.** No longer avoidable. | Prefer the longest-lived token available; heartbeat alerts on auth failure; treat a missed day as missing data, never as "no signal". |
| 9 | **Chain staleness = 39% of the whole 1-SD signal at 5 min.** | §2.7. 60s staleness gate; feed timestamp recorded on every decision and shown in results. |
| 10 | **Costs = 0.735% of premium (STT 0.15% from 1 Apr 2026).** Real, but Rev 1 overstated it. | Hand-written `costs.py`; unit-tested against a real contract note; gross and net always side by side. |
| 11 | **Optimistic fills.** | Buy at ask, sell at bid, through `liquidity.py`, plus the open penalty. Modelled spreads logged as modelled. |
| 12 | **Lookahead bias.** | Engine hands strategies a strictly point-in-time view; no bar with `ts > now` reachable. Asserted in tests. |
| 13 | **BANKNIFTY is a worse instrument, not a second sample.** Monthly-only, 5.8x spread at +1, 100% open dislocation. | §1.2. Demoted to secondary. NIFTY first. |
| 14 | **DTE>=5 reduces the gamma convexity that makes intraday long options pay.** | Honest trade-off of the medium-risk choice. DTE is a first-class input; results reported per DTE bucket. |
| 15 | **Silent failure on the VPS.** A dead cron reads identically to "no signals today." | Daily heartbeat row + "last successful run" on the dashboard. Absence is visible. |
| 16 | **Lot sizes and freeze limits change.** | `contracts.py` holds dated values; §1.1 verified 2026-08-28. |
| 17 | **Kite cannot supply expired options data at any price.** | Confirmed from Zerodha's own docs. Kite for live only; backtest per §5.1. |
| 18 | **Horizon mismatch: stops sized to 45 min, but a 09:15-09:30 range breakout enters ~09:32 with 28 min left.** Monte Carlo on the Rev 1 spec: **78-82% of ORB/VWAP trades exit on the clock**, not on thesis. | §3.6. Exit distances computed from `10:00 - entry_time`, not a constant. **Timeout rate is a first-class reported metric per config.** |
| 19 | **The 45-min window carries 18.85% of session variance, not the 12% √t implies.** Rev 1's 0.346 stop factor was ~25% too tight, inflating stop-outs on top of #18. | §2.1, §3.6. Factor corrected to **0.434**; Phase 0 item 6 re-estimates it from our own bars each quarter rather than trusting a literature constant. |

### Legal / licensing notes

- **PyAlgoMate** contains `920Straddle.py` — almost exactly this spec — but ships **no LICENSE
  file**, meaning all rights reserved. Same for two other close matches. **Read as specification
  only; copy no code.**
- **jugaad-data** ships `LICENSE.YOLO.md`, not an OSI-standard licence. Fine for personal
  self-hosted use; review before any commercial use.
- Informal Telegram/Gumroad options-data sellers: **skip.** Almost certainly violating NSE
  redistribution licensing, unverifiable lineage, irreversible UPI payment.

### Open source: used and rejected

**Use:** official broker SDK or raw `httpx`, `py_vollib` (now required for the §2.3 vega model).
(`jugaad-data` was slated for holidays + EOD but dropped at Phase 0a build time: non-OSI licence
as noted below, and holidays are a static annual list better hardcoded from the circulars than
fetched through a third-party scraper at runtime.)

**Rejected, with reason:** `optopsy` — `normalize_dates()` calls `dt.normalize()`, flooring every
timestamp to midnight, so intraday is architecturally impossible. `OpenAlgo` — real paper engine
but 151 pinned deps and **2GB RAM minimum**, exceeding the VPS. `vectorbt`/`backtrader`/`zipline`/
`bt` — no option instrument model; backtrader's last real commit Apr 2023. `nautilus_trader`/
`Lean` — excellent options support at 255MB/586MB, hedge-fund scale. `lumibot`/`optionlab` —
51 deps incl. `openai`; optionlab hard-depends on Jupyter. `mibian` — unmaintained since 2021
*and* unlicensed. `nsepy` — PyPI release **March 2020**, broken for years despite topping search
results.

**Worth reading before writing our own:** `sirnfs/OptionSuite` (MIT) for its
Option→MultiLegOption→Portfolio model; `marketcalls/ExpiryFlow` (MIT) as the reference for
Dhan's expired-options paging.

---

## 8. Errors in Rev 1, listed rather than deleted

Kept visible so the correction record survives, and so the same mistakes are not re-made.

| Rev 1 claim | Correction |
|---|---|
| §3.1: 2–3 strikes OTM has δ ≈ 0.10–0.15 | **δ ≈ 0.34** at DTE 7. Off by ~3× |
| §3.1: OTM gain "inside the spread" | Gain ~28 pts vs measured spread 0.33–0.55 pts. Wrong |
| §3.1: override Varsity's far-OTM advice | **Withdrawn.** % gain rises with OTM-ness. Now a parameter |
| §2: 45-min 1SD = 0.31% | **0.292%** at VIX 10.68 — right answer, wrong twice over. Two errors of 1.33× and 1.57× in opposite directions nearly cancelled (§2.1) |
| §2: scale to 45 min with `√(45/375) = 0.346` | **0.434**, measured. √t understates the open by 1.57×. Stops were **~25% too tight** |
| §2: annualise with `√365` in the formula (while the table used √252) | **√252.** Formula and table disagreed by ~20%; the table was right |
| §2: the session is 375 minutes | **385.** Close moved to 15:40 effective 03-Aug-2026. Any `/375` in code is stale |
| §2: theta ≈ 0.6 pts, "theta is dead" | **1.25 pts** trading-time, ~3.5% of the signal. Small, not dead |
| §6 #1: costs can flip a strategy "firmly negative" | **0.735% of premium**; 3–17% of a 1-SD win depending on spread. Overstated |
| Lot sizes (implicitly 75/35) | **65 / 30** |
| BANKNIFTY weeklies assumed possible | **Discontinued.** Monthly, last Tuesday |
| STT unresolved | **0.15% sell-side premium**, 1 Apr 2026 |
| §3.3 "the opening-hour timing thesis is ours" | Overclaim. Zarattini et al. exist — but weak, US equities, vendor-authored |
| §4.2 "Auth: none needed" framed as a benefit | **ToU violation.** Unauthenticated ≠ licensed |
| §4.2 "Why not Kite… would buy nothing" | Wrong for the **live** feed. Right for backtest |
| 10 configs × 2 indices = 20 variants | **6 configs, NIFTY only.** 20 manufactures Sharpe 1.18 from noise |
| §3.5 exits assume SL-M and market orders | **Both illegal/unavailable in options.** Limit orders only |
| Straddle "conditional 4th" | **Out.** Max long vega at the daily IV maximum |
| Fill model = "buy at ask, sell at bid" | Insufficient. `liquidity.py`: no-quote failure, open penalty, staleness gate |
| §3.5 exits sized to the full 45-min window regardless of entry time | **Horizon mismatch.** ~28 min actually remain after an ORB trigger; 78–82% of trades would exit on the clock (§3.6, loophole #18) |
| §3.3 the timing thesis has "no published support" | There is published support, and it is worse than none: crude-oil-only peer review with unstable sub-periods, and an Indian null at bootstrap p ≈ 0.5 (§3.4) |

---

## 9. What this plan does *not* claim

- **No live trading.** Paper only. No order-placement code path will exist.
- **No claim of a Varsity-endorsed opening-hour edge.** Varsity has zero content on the open and
  prescribes 3:20 PM entries. The structures are Varsity-derived; the timing is not.
- **No claim that a positive backtest predicts live results.** The backtest is a negative filter
  only (§5).
- **No claim that the strategies will be profitable.** SEBI's Aug 2026 study finds **0.5%**
  sustained profitability over FY22–FY26. The prior is strongly against us, and the design is
  built to detect that rather than paper over it.
- **Ranking is provisional until forward paper trading confirms it.** A "top N" from historical
  data is a hypothesis, not a result.
- **No claim that six months of forward paper trading can confirm anything.** Per §5.2 it is
  underpowered by roughly an order of magnitude. It validates the machinery and rejects large
  negative expectancy. That is all it can do.

---

## 10. Execution sequence, and the division of labour

Phases are gated, not scheduled: each one has an exit condition, and a phase that fails its gate
stops the project rather than degrading into the next one.

### Phase 0a — Foundations that depend on nothing (no cost, starts immediately)

| Item | Output | Gate | Status (2026-08-30) |
|---|---|---|---|
| VPS verification | Linode region confirmed, RAM known, updates applied, reboot done | Host reachable and in a region the broker serves | ✅ 1 GB RAM, Ubuntu 26.04, kernel 7.0.0-30, rebooted clean (grub-pc repaired). Region check pending |
| `calendar.py` | Trading days, NSE holidays **hardcoded from circulars** (jugaad-data dropped), DTE>=5 resolver | Resolver reproduces §1.3's table exactly, in tests | ✅ built, tested |
| `contracts.py` | Dated lot sizes, freeze limits, strike steps, tick size | Matches §1.1 | ✅ built, tested (incl. BANKNIFTY's 35-lot window Apr–Dec 2025 the doc omitted) |
| `costs.py` | Full Indian cost stack, **STT keyed by trade date across all three regimes**, plus index-futures legs | **Reproduces a real contract note to the paisa** — needs your input | ✅ **GATE CLOSED 2026-08-30** against a real Jun-2024 BANKNIFTY futures note, to the paisa. The note broker-confirmed: STT whole-rupee rounding, GST base includes SEBI (3.16 vs 3.10 discrimination), IPFT bundled into the exchange-txn line, and resolved the 3,552.99-vs-3,553 precision question (0.03553% = txn + IPFT bundled). Options-specific *rate values* remain circular-sourced; a placeholder test stays skipped for a future options note |
| Bhavcopy archive | Official NSE F&O EOD, backfilled | Per-strike OHLC available offline for cross-checks | ✅ built (≤3 req/min, archives-only per §6), tested offline |

**Expiry-rule resolution (found at build time):** §1's "never expiry day" and §1.3's Tuesday row
(roll to DTE 7) do not contradict once split: `resolve_expiry()` implements §1.3's ladder;
`is_tradeable()` additionally refuses expiry day itself, the stricter §1 rule. Both are asserted
in tests.

**Least-certain facts in the built code** (everything else traces to a named circular/Act):
the pre-Oct-2024 NSE txn rate of 0.053% (broker-published, no circular line found), the
2026-01-15 holiday (one mirror omits it; annotated in source), and the 2016 STT rate (only
matters if a backtest ever reaches that far back).

### Phase 0b — Live capture (needs the Kite Connect subscription)

Capture only. No strategies, no decisions, no P&L. `broker.py` writes full chain snapshots to
SQLite every session, 09:15–10:00, for **10 sessions minimum**.

This single step pays for itself four times: it measures the 09:15–09:30 spreads that no primary
source publishes (Phase 0 item 4), it measures real feed latency against the 60s staleness gate
(item 2), it starts the bar archive needed to re-estimate the 0.434 factor (item 6), and it
proves the unattended VPS pipeline works before any strategy logic depends on it.

**Gate:** measured spreads are within the same order as §1.2's EOD figures. If opening spreads
turn out to be 5–10× the EOD numbers, the §2.6 cost table is wrong and the economics must be
re-derived before writing a single strategy.

**Status 2026-08-30: code built, not yet deployed.** `broker.py` (Kite auth via raw httpx —
`kiteconnect` SDK deliberately not imported so the order-write API is *unimportable* from this
package, enforced by a permanent audit test) and `capture.py` (5s batched quote cycle, ATM±5 ×
CE/PE × DTE≥5 expiries × both indices ≈ 88 keys/cycle vs Kite's 500/call limit; empty books
stored NULL per §2.5; exchange `feed_ts` kept for §2.7; hard stop 10:05; captures every trading
day including days `is_tradeable` would refuse — data is data). systemd templates + runbook in
`deploy/`. Kite Connect subscribed; keys in `.env` (gitignored). Remaining before first capture:
deploy to the Linode, one interactive login to mint the first token, one live morning.

### Phase 0c — ~~The data question that decides the project~~ WITHDRAWN 2026-08-30

The expired-options backtest is **dropped by decision**, not by vendor failure: forward-only
paper trading from live capture, plus a **NIFTY index-level signal test** on Kite historical
index candles (included in the Rs 500/mo Connect plan at no extra cost) to supply the
statistical power §5.2 shows forward paper cannot. The index test asks "does a 09:15–09:30
range break predict direction over the next 28 minutes?" as a hit-rate test — years of index
minute bars, no relative-strike problem, no Rs 499/mo Dhan subscription. Options-level
monetisation after costs is then Phase 3's question, asked only if the index-level signal
exists. §5.2's power table still governs: anything the index test cannot reject in years of
data is not rescued by months of forward paper.

### Phase 1 — The engine (~700 LOC, no market dependency)

`engine.py`, `position.py`, `liquidity.py`, `strategies.py`, `metrics.py`, plus tests. The 6
configs of §3.5 are **committed and the commit hash recorded before any backtest runs** — that
hash is the pre-registration record (§5 control 1).

**Gate:** lookahead assertion passes; every fill provably routes through `liquidity.py`; costs
reconcile against the contract note; timeout rate is reported per config.

### Phase 2 — Backtest as a negative filter

Walk-forward, most recent 6 months held out untouched, gross and net side by side, deflated
Sharpe. Configs are **eliminated**, never certified.

**Gate:** a config survives only with net-of-cost positive expectancy *and* a deflated Sharpe
above zero on out-of-sample windows. Expect survivors to be few or none. None is a valid result.

### Phase 3 — Forward paper trading

Daily unattended run, 09:15–10:00, dashboard live. Survivors from Phase 2 plus, deliberately,
**one config Phase 2 rejected** — as a control that the live pipeline can reproduce a known bad
result. If the known-bad config looks good live, the live pipeline is broken.

### Phase 4 — Review gates

- **Month 1:** infrastructure only. Do modelled fills match observed quotes? Do costs match? Is
  there a day with no heartbeat?
- **Month 3:** first P&L read, explicitly labelled underpowered per §5.2.
- **Month 6:** the verdict. Given §5.2, the honest possible outcomes are "large negative
  expectancy, rejected", "consistent with zero — the expected result", or "anomalously large,
  therefore assume a bug until proven otherwise."

### Your manual tasks

Everything below is something I cannot do for you. Ordered by what blocks what.

| # | Task | Blocks | Cost |
|---|---|---|---|
| 1 | **Kite Connect subscription.** Create an app at `developers.kite.trade`, get `api_key` + `api_secret`. Note: your existing Zerodha trading account does **not** include this | Phase 0b, Phase 3 | Rs 500/mo |
| 2 | **Supply a real Zerodha options contract note** from any past options trade — the charges breakdown, not the P&L | `costs.py` gate in Phase 0a | free |
| 3 | **Decide on expired-options data** (Dhan Rs 499/mo or alternative), after reading §5.2 on what is lost without it | Phase 0c, and therefore Phase 2 | Rs 499/mo |
| 4 | **Approve the VPS reboot** (53 pending updates, restart required) | Phase 0a | free |
| 5 | **Daily broker login.** Kite's token expires every morning (~07:30 IST). Unattended operation requires either a manual login before 09:15 each trading day, or automating TOTP — which Zerodha discourages. **This is a genuine daily commitment and the largest ongoing operational cost of the project** | Phase 3, every day | your time |

Item 5 deserves emphasis: it is the one part of this that cannot be engineered away, and it is
worth deciding *now* whether a daily pre-market login is something you will still be doing in
month five. If not, that changes the design before it is built, not after.
