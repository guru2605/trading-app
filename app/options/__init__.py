"""Options paper-trading support package (Phase 0a + 0b).

Read-only, research-grade primitives for NSE index options:

- :mod:`app.options.calendar`  — NSE trading calendar, session bounds, expiry ladder, DTE resolver
- :mod:`app.options.contracts` — NIFTY / BANKNIFTY contract specs and tradingsymbol handling
- :mod:`app.options.costs`     — itemised Indian cost stack for index options and futures, keyed by trade date
- :mod:`app.options.bhavcopy`  — local archive of NSE's official published F&O bhavcopy
- :mod:`app.options.broker`    — Kite Connect auth for the capture pipeline (not re-exported here)
- :mod:`app.options.capture`   — Phase 0b 09:15-10:00 chain-snapshot capture (not re-exported here)

``broker`` and ``capture`` are deliberately not imported at package level so that consumers
of the calendar/contracts/costs primitives do not pull in FastAPI or need broker credentials.

PAPER TRADING ONLY. Nothing in this package places, modifies or cancels an order, and no
broker write API is referenced anywhere in it — enforced by the source audit in
tests/test_options_capture.py.
"""

from app.options.calendar import (
    IST,
    SESSION_CLOSE,
    SESSION_MINUTES,
    SESSION_OPEN,
    WINDOW_CLOSE,
    WINDOW_OPEN,
    dte,
    is_expiry_day,
    is_holiday,
    is_tradeable,
    is_trading_day,
    resolve_expiry,
    session_bounds,
)
from app.options.contracts import (
    Index,
    OptionType,
    atm_strike,
    build_tradingsymbol,
    lot_size,
    parse_tradingsymbol,
    strike_at_offset,
)
from app.options.costs import CostBreakdown, CostLine, Side, futures_leg_costs, leg_costs, round_trip_costs

__all__ = [
    "IST",
    "SESSION_CLOSE",
    "SESSION_MINUTES",
    "SESSION_OPEN",
    "WINDOW_CLOSE",
    "WINDOW_OPEN",
    "CostBreakdown",
    "CostLine",
    "Index",
    "OptionType",
    "Side",
    "atm_strike",
    "build_tradingsymbol",
    "dte",
    "futures_leg_costs",
    "is_expiry_day",
    "is_holiday",
    "is_tradeable",
    "is_trading_day",
    "leg_costs",
    "lot_size",
    "parse_tradingsymbol",
    "resolve_expiry",
    "round_trip_costs",
    "session_bounds",
    "strike_at_offset",
]
