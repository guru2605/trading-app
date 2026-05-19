# Kite Trader — Personal Trading App

## 1. Vision

A personal trading application that integrates with Zerodha's Kite Connect API to provide a live risk cockpit, behavioral trade journaling, custom alerts, risk-gated order automation, and Indian-tax-aware reporting — all from a single self-hosted service.

**Design Principles:**
- Safety-first: every order passes through a risk engine before execution
- Observability: every state change is recorded as an immutable audit event
- Self-awareness: the system surfaces your behavioral patterns, not just your P&L

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│                  React + Vite + TailwindCSS                 │
│         (Dashboard, Journal UI, Alert Config, Reports)      │
└────────────────────────┬────────────────────────────────────┘
                         │ REST (JSON)
┌────────────────────────▼────────────────────────────────────┐
│                     FastAPI Backend                          │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │Risk      │ │ Journal  │ │ Alerts & │ │    Orders     │  │
│  │Cockpit   │ │+Behavior │ │ Screener │ │    Module     │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬────────┘  │
│       │             │            │               │          │
│  ┌────▼─────────────▼────────────▼───────────────▼────────┐ │
│  │              Risk Engine (pre-order gate)               │ │
│  └────────────────────────┬───────────────────────────────┘ │
│                           │                                 │
│  ┌────────────────────────▼───────────────────────────────┐ │
│  │              Kite Connect Service Layer                 │ │
│  │         (Auth, REST client, WebSocket client)           │ │
│  └────────────────────────┬───────────────────────────────┘ │
│                           │                                 │
│  ┌────────────────────────▼───────────────────────────────┐ │
│  │               Audit Event Log (append-only)            │ │
│  └────────────────────────┬───────────────────────────────┘ │
│                           │                                 │
│  ┌────────────────────────▼───────────────────────────────┐ │
│  │                   Tax Engine                           │ │
│  │       (STCG/LTCG, Wash Sale, Daily Estimation)        │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────────┬──────────────┬─────────────────────┘
                         │              │
              ┌──────────▼──┐    ┌──────▼──────┐
              │ PostgreSQL  │    │   Redis     │
              │ (persistent)│    │ (ticks,     │
              │             │    │  sessions)  │
              └─────────────┘    └─────────────┘
                                        │
                                 ┌──────▼──────┐
                                 │  Telegram   │
                                 │  Bot API    │
                                 └─────────────┘
```

---

## 3. Tech Stack

| Layer          | Choice                        | Rationale                                      |
|----------------|-------------------------------|-------------------------------------------------|
| Language       | Python 3.12                   | First-class Kite SDK support, workspace standard|
| Framework      | FastAPI                       | Async-native, OpenAPI docs out of the box       |
| Deps           | Poetry                        | Workspace standard                              |
| Database       | PostgreSQL 16                 | Relational data (trades, journal, alerts)       |
| Cache/Pub-Sub  | Redis 7                       | Tick caching, session store, pub/sub for alerts |
| ORM            | SQLAlchemy 2.0 (async)        | Mature, typed, async support                    |
| Migrations     | Alembic                       | De-facto standard for SQLAlchemy                |
| Broker SDK     | kiteconnect 5.x               | Official Zerodha Python SDK                     |
| Task Scheduler | APScheduler                   | Lightweight, in-process, cron-like scheduling   |
| Notifications  | python-telegram-bot           | Telegram alerts                                 |
| Frontend       | React 18 + Vite + TailwindCSS | Fast dev, clean UI                              |
| Charts         | Recharts                      | Simple, React-native charting                   |
| Containerization| Docker + docker-compose      | Local dev parity                                |
| Testing        | pytest + pytest-asyncio       | Workspace standard                              |
| Linting        | Ruff                          | Fast, replaces black + isort + flake8           |
| Type checking  | mypy                          | Workspace standard                              |

---

## 4. Project Structure

```
kite-trader/
├── PLAN.md
├── pyproject.toml
├── poetry.lock
├── Makefile
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── tasks.sh
├── .env.example
│
├── alembic/
│   └── versions/
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings via pydantic-settings
│   ├── deps.py                  # Dependency injection (db session, kite client)
│   │
│   ├── kite/                    # Kite Connect integration layer
│   │   ├── __init__.py
│   │   ├── auth.py              # OAuth flow, token refresh, TOTP helper
│   │   ├── client.py            # Thin wrapper around KiteConnect SDK
│   │   └── websocket.py         # KiteTicker management (connect, reconnect, subscribe)
│   │
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── holding.py
│   │   ├── position.py
│   │   ├── order.py
│   │   ├── trade.py
│   │   ├── journal_entry.py
│   │   ├── alert.py
│   │   ├── instrument.py
│   │   ├── audit_event.py       # Immutable audit log entries
│   │   └── risk_state.py        # Daily drawdown, exposure snapshots
│   │
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── portfolio.py
│   │   ├── journal.py
│   │   ├── alert.py
│   │   ├── order.py
│   │   ├── tax.py
│   │   ├── risk.py
│   │   └── audit.py
│   │
│   ├── routers/                 # FastAPI route handlers
│   │   ├── __init__.py
│   │   ├── auth.py              # GET /auth/login, GET /auth/callback
│   │   ├── portfolio.py         # GET /portfolio/holdings, /positions, /orders
│   │   ├── journal.py           # CRUD /journal/entries
│   │   ├── alerts.py            # CRUD /alerts, GET /alerts/triggered
│   │   ├── orders.py            # POST /orders/place, DELETE /orders/{id}
│   │   ├── tax.py               # GET /tax/report, /tax/summary
│   │   ├── risk.py              # GET /risk/exposure, POST /risk/panic
│   │   └── audit.py             # GET /audit/events
│   │
│   ├── services/                # Business logic
│   │   ├── __init__.py
│   │   ├── portfolio.py         # Sync holdings/positions, compute P&L
│   │   ├── correlation.py       # Sector/stock correlation detection
│   │   ├── journal.py           # Auto-import trades, CRUD, analytics
│   │   ├── behavior.py          # Behavioral pattern detection engine
│   │   ├── alerts.py            # Evaluate alert conditions against ticks
│   │   ├── screener.py          # Technical indicator calculations
│   │   ├── risk_engine.py       # Pre-order risk gate + exposure tracking
│   │   ├── safety.py            # Panic button, kill switches, circuit breakers
│   │   ├── order_automation.py  # Rule engine for conditional orders
│   │   ├── tax.py               # STCG/LTCG calculation, wash sale, daily estimation
│   │   ├── audit.py             # Append-only event logging
│   │   └── notifications.py    # Telegram bot integration
│   │
│   ├── tasks/                   # Scheduled background jobs
│   │   ├── __init__.py
│   │   ├── sync_trades.py       # Daily trade sync from Kite
│   │   ├── sync_instruments.py  # Daily instrument master download
│   │   ├── daily_tax_snapshot.py # Daily tax liability estimation
│   │   ├── behavior_analysis.py # End-of-day behavioral pattern scan
│   │   └── scheduler.py        # APScheduler setup
│   │
│   └── db/
│       ├── __init__.py
│       ├── session.py           # Async engine + sessionmaker
│       └── base.py              # Declarative base
│
├── frontend/                    # React app (separate build)
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Journal.tsx
│   │   │   ├── Alerts.tsx
│   │   │   ├── Orders.tsx
│   │   │   └── TaxReport.tsx
│   │   ├── components/
│   │   │   │   ├── HoldingsTable.tsx
│   │   │   ├── PLChart.tsx
│   │   │   ├── SectorAllocation.tsx
│   │   │   ├── CorrelationMatrix.tsx
│   │   │   ├── ExposureMeter.tsx
│   │   │   ├── TradeJournalForm.tsx
│   │   │   ├── BehaviorInsights.tsx
│   │   │   ├── AlertRuleBuilder.tsx
│   │   │   ├── PanicButton.tsx
│   │   │   ├── RiskDashboard.tsx
│   │   │   ├── AuditLog.tsx
│   │   │   └── TaxSummaryCard.tsx
│   │   ├── hooks/
│   │   │   └── useKiteData.ts
│   │   └── api/
│   │       └── client.ts        # Axios/fetch wrapper
│   └── tailwind.config.js
│
└── tests/
    ├── conftest.py
    ├── test_portfolio.py
    ├── test_correlation.py
    ├── test_journal.py
    ├── test_behavior.py
    ├── test_alerts.py
    ├── test_risk_engine.py
    ├── test_safety.py
    ├── test_orders.py
    ├── test_audit.py
    └── test_tax.py
```

---

## 5. Database Schema

```sql
-- Instruments master (refreshed daily from Kite)
CREATE TABLE instruments (
    instrument_token  BIGINT PRIMARY KEY,
    exchange          VARCHAR(10) NOT NULL,
    tradingsymbol     VARCHAR(50) NOT NULL,
    name              VARCHAR(100),
    segment           VARCHAR(20),
    instrument_type   VARCHAR(20),
    lot_size          INT DEFAULT 1,
    last_updated      TIMESTAMPTZ DEFAULT now()
);

-- Persisted holdings snapshot
CREATE TABLE holdings (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tradingsymbol     VARCHAR(50) NOT NULL,
    exchange          VARCHAR(10) NOT NULL,
    isin              VARCHAR(20),
    quantity          INT NOT NULL,
    average_price     NUMERIC(12,2) NOT NULL,
    last_price        NUMERIC(12,2),
    pnl               NUMERIC(12,2),
    day_change_pct    NUMERIC(6,2),
    synced_at         TIMESTAMPTZ DEFAULT now()
);

-- Executed trades (auto-imported from Kite)
CREATE TABLE trades (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id          VARCHAR(50) NOT NULL,
    exchange_order_id VARCHAR(50),
    tradingsymbol     VARCHAR(50) NOT NULL,
    exchange          VARCHAR(10) NOT NULL,
    segment           VARCHAR(20),
    transaction_type  VARCHAR(4) NOT NULL,        -- BUY / SELL
    quantity          INT NOT NULL,
    price             NUMERIC(12,2) NOT NULL,
    product           VARCHAR(10) NOT NULL,        -- CNC / MIS / NRML
    order_type        VARCHAR(10) NOT NULL,        -- MARKET / LIMIT / SL
    traded_at         TIMESTAMPTZ NOT NULL,
    synced_at         TIMESTAMPTZ DEFAULT now(),
    UNIQUE(order_id, exchange_order_id)
);

-- Trade journal entries (user-authored, linked to trades)
CREATE TABLE journal_entries (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id          UUID REFERENCES trades(id),
    tradingsymbol     VARCHAR(50),
    strategy          VARCHAR(50),                 -- e.g., momentum, swing, earnings
    tags              TEXT[],
    entry_rationale   TEXT,
    exit_rationale    TEXT,
    emotional_state   VARCHAR(20),                 -- calm, fomo, fearful, confident
    outcome           VARCHAR(10),                 -- win, loss, breakeven
    notes             TEXT,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

-- Alert rules
CREATE TABLE alerts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tradingsymbol     VARCHAR(50) NOT NULL,
    instrument_token  BIGINT NOT NULL,
    condition_type    VARCHAR(20) NOT NULL,        -- price_above, price_below, volume_spike, rsi_cross
    threshold         NUMERIC(12,4) NOT NULL,
    is_active         BOOLEAN DEFAULT TRUE,
    is_triggered      BOOLEAN DEFAULT FALSE,
    triggered_at      TIMESTAMPTZ,
    notify_telegram   BOOLEAN DEFAULT TRUE,
    created_at        TIMESTAMPTZ DEFAULT now()
);

-- Automation rules for conditional orders
CREATE TABLE order_rules (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(100) NOT NULL,
    tradingsymbol     VARCHAR(50) NOT NULL,
    exchange          VARCHAR(10) NOT NULL,
    condition         JSONB NOT NULL,              -- {"type": "price_drop_pct", "reference": "open", "value": 1.0}
    action            JSONB NOT NULL,              -- {"side": "BUY", "qty": 50, "product": "MIS", "order_type": "MARKET"}
    is_active         BOOLEAN DEFAULT TRUE,
    last_executed_at  TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT now()
);

-- Audit event log (append-only, never updated or deleted)
CREATE TABLE audit_events (
    id                BIGSERIAL PRIMARY KEY,
    event_type        VARCHAR(50) NOT NULL,        -- order.placed, order.rejected, order.filled,
                                                   -- rule.triggered, alert.fired, risk.blocked,
                                                   -- safety.panic, auth.login, sync.completed
    entity_type       VARCHAR(20),                 -- order, rule, alert, holding, position
    entity_id         VARCHAR(50),                 -- FK to the relevant entity
    payload           JSONB NOT NULL,              -- full event data snapshot
    source            VARCHAR(20) NOT NULL,        -- manual, automation, system, kite_callback
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_audit_event_type ON audit_events(event_type);
CREATE INDEX idx_audit_created_at ON audit_events(created_at);

-- Risk state (daily snapshot, one row per trading day)
CREATE TABLE risk_snapshots (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_date        DATE NOT NULL UNIQUE,
    total_exposure    NUMERIC(14,2) NOT NULL,       -- sum of all open position values
    sector_exposure   JSONB NOT NULL,               -- {"Financials": 45.2, "IT": 22.1, ...}
    correlation_score NUMERIC(4,2),                 -- 0-1, how correlated the portfolio is
    realized_pnl      NUMERIC(12,2) DEFAULT 0,     -- day's realized P&L
    unrealized_pnl    NUMERIC(12,2) DEFAULT 0,     -- day's unrealized P&L
    max_drawdown      NUMERIC(12,2) DEFAULT 0,     -- intraday peak-to-trough
    orders_placed     INT DEFAULT 0,
    orders_rejected   INT DEFAULT 0,
    risk_blocks       INT DEFAULT 0,                -- how many orders the risk engine blocked
    safety_triggered  BOOLEAN DEFAULT FALSE,        -- was panic/kill switch activated?
    created_at        TIMESTAMPTZ DEFAULT now()
);

-- Behavioral flags (detected patterns per day)
CREATE TABLE behavior_flags (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_date        DATE NOT NULL,
    flag_type         VARCHAR(30) NOT NULL,         -- revenge_trade, overtrade, cut_winner,
                                                    -- avg_loser, fomo_entry, size_spike
    severity          VARCHAR(10) NOT NULL,          -- info, warning, critical
    description       TEXT NOT NULL,                 -- human-readable explanation
    evidence          JSONB NOT NULL,                -- supporting data (trade_ids, timestamps, metrics)
    acknowledged      BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_behavior_date ON behavior_flags(trade_date);

-- Sector classification lookup
CREATE TABLE sector_map (
    isin              VARCHAR(20) PRIMARY KEY,
    tradingsymbol     VARCHAR(50) NOT NULL,
    sector            VARCHAR(50) NOT NULL,
    industry          VARCHAR(50),
    last_updated      TIMESTAMPTZ DEFAULT now()
);

-- Tax lots for FIFO-based gain calculation
CREATE TABLE tax_lots (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tradingsymbol     VARCHAR(50) NOT NULL,
    buy_trade_id      UUID REFERENCES trades(id),
    sell_trade_id     UUID REFERENCES trades(id),
    quantity          INT NOT NULL,
    buy_price         NUMERIC(12,2) NOT NULL,
    sell_price        NUMERIC(12,2),
    buy_date          DATE NOT NULL,
    sell_date         DATE,
    holding_period    INT,                         -- days
    gain_type         VARCHAR(4),                  -- STCG / LTCG (equity LTCG if > 365 days)
    gain_amount       NUMERIC(12,2),
    is_wash_sale      BOOLEAN DEFAULT FALSE,
    financial_year    VARCHAR(9)                   -- e.g., 2025-2026
);
```

---

## 6. Feature Specifications

### Feature 1: Portfolio & Holdings Dashboard → "Live Risk Cockpit"

**Kite API endpoints used:**
- `kite.holdings()` — delivery holdings
- `kite.positions()` — intraday + overnight positions
- `kite.orders()` — today's order book
- `kite.trades()` — today's executed trades

**Backend:**
- `GET /api/portfolio/holdings` — returns holdings with live P&L
- `GET /api/portfolio/positions` — returns net positions with day P&L
- `GET /api/portfolio/orders` — returns order history (today)
- `GET /api/portfolio/summary` — aggregated P&L, investment value, current value
- `GET /api/portfolio/allocation` — sector-wise and segment-wise breakdown
- `GET /api/portfolio/correlation` — correlation analysis across holdings
- `GET /api/portfolio/exposure` — total exposure, leverage utilization, directional bias
- `POST /api/portfolio/sync` — force re-sync from Kite

**Sector mapping:**
- Download NSE sector classification CSV (one-time, refresh monthly)
- Store in `sector_map` table, join with holdings on ISIN/tradingsymbol

**Correlation Detection:**
- Fetch 90-day historical closing prices for all held symbols (Kite historical data API)
- Compute pairwise Pearson correlation matrix using `numpy`
- Flag concentration risk when >60% of portfolio value is in stocks with correlation >0.7
- Example output:
  ```
  WARNING: 78% of portfolio is financial-sector correlated
  HDFC (32%) + ICICI (24%) + SBI (14%) + BANKBEES (8%)
  Correlation: 0.82 avg pairwise
  ```
- Store daily correlation_score in `risk_snapshots`

**Exposure Engine:**
- Total exposure = sum of abs(position_value) across all open positions
- Directional bias = (long_value - short_value) / total_exposure
- Leverage = total_exposure / account_equity (from `kite.margins()`)
- Overnight risk = CNC + NRML position value (positions carried overnight)

**Logic:**
- On each sync, fetch holdings/positions from Kite, upsert into local DB
- Compute total invested, current value, day P&L, overall P&L
- Run correlation analysis on holdings
- Compute exposure metrics
- Snapshot into `risk_snapshots` table
- Group by sector/segment for allocation pie chart

**Frontend:**
- Summary cards: Total Value, Day P&L, Overall P&L, XIRR
- Exposure meter: gauge showing leverage utilization (green/yellow/red zones)
- Correlation matrix: heatmap of pairwise stock correlations
- Concentration warning banner (when triggered)
- Holdings table: sortable by symbol, P&L, % change, sector
- Sector allocation: pie/donut chart (Recharts)
- Positions table: with product type filter (MIS/CNC/NRML)

---

### Feature 2: Trade Journal → "Behavior Analytics Engine"

**Backend:**
- `GET /api/journal/entries` — list entries with filters (date range, strategy, outcome, symbol)
- `GET /api/journal/entries/{id}` — single entry detail
- `POST /api/journal/entries` — create entry (manually or linked to trade_id)
- `PUT /api/journal/entries/{id}` — update entry
- `DELETE /api/journal/entries/{id}` — soft delete
- `POST /api/journal/import` — auto-import today's trades as draft journal entries
- `GET /api/journal/analytics` — win rate, avg gain/loss, performance by strategy/tag/time
- `GET /api/journal/behavior` — detected behavioral patterns and flags
- `PUT /api/journal/behavior/{id}/acknowledge` — mark a behavioral flag as seen

**Auto-import logic:**
- Scheduled task runs at 3:45 PM IST (after market close)
- Fetch all trades via `kite.trades()`
- Group by order_id to pair BUY+SELL legs
- Create draft journal entries with pre-filled symbol, price, qty, time
- User completes rationale, strategy, tags via the UI

**Analytics queries:**
- Win rate = count(outcome='win') / total
- Avg win size vs avg loss size
- Performance grouped by: strategy, tag, day-of-week, hour-of-day
- Streak tracking (consecutive wins/losses)

**Behavioral Detection Engine (rule-based, runs end-of-day):**

| Pattern             | Detection Logic                                                           | Severity |
|---------------------|---------------------------------------------------------------------------|----------|
| Revenge trading     | Loss trade followed by a new trade in <5 min on same/different symbol     | critical |
| Overtrading         | >N trades in a single day (configurable, default 15)                      | warning  |
| Cutting winners     | Profitable position closed with gain <1% while unrealized gain was >3%    | warning  |
| Averaging losers    | Additional BUY on a symbol already showing >2% unrealized loss            | critical |
| FOMO entry          | BUY after price already moved >3% from day's open                         | info     |
| Position size spike | Single trade value >2x the user's average trade size (30-day rolling)     | warning  |
| Loss streak         | 3+ consecutive losing trades in a day                                      | warning  |

**Detection flow:**
1. End-of-day task fetches all trades for the day from DB
2. Runs each detection rule against the trade sequence
3. Stores detected patterns in `behavior_flags` table with evidence (trade_ids, timestamps)
4. Sends Telegram summary: "2 behavioral flags today: 1 revenge trade, 1 overtrading"

**Hidden alpha detection (weekly):**
- Aggregate journal entries by: strategy + day-of-week + hour
- Compute expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
- Surface top-performing combos:
  ```
  Your opening breakout trades on Thursdays have 68% win rate
  with 2.1x reward-to-risk. Expectancy: +₹1,240/trade
  ```

**Frontend:**
- Journal list with filters and search
- Entry form: trade details (auto-filled) + strategy dropdown + tags (multi-select) + free-text notes + emotional state selector
- Behavior insights panel: today's flags with severity badges, acknowledge button
- Analytics dashboard: win rate donut, strategy performance bar chart, calendar heatmap
- Weekly insight card: "Your best edge this week"

---

### Feature 3: Custom Alerts & Screener

**Kite API used:**
- `KiteTicker` WebSocket — subscribe to instrument tokens for live ticks

**Backend:**
- `POST /api/alerts` — create alert rule
- `GET /api/alerts` — list all rules (active/triggered)
- `PUT /api/alerts/{id}` — update rule
- `DELETE /api/alerts/{id}` — deactivate rule
- `GET /api/alerts/triggered` — history of triggered alerts

**Alert condition types:**
| Type            | Logic                                                  |
|-----------------|--------------------------------------------------------|
| `price_above`   | `last_price >= threshold`                              |
| `price_below`   | `last_price <= threshold`                              |
| `volume_spike`  | `volume > threshold * avg_volume_20d`                  |
| `rsi_cross_up`  | RSI(14) crosses above threshold (e.g., 30 = oversold)  |
| `rsi_cross_down`| RSI(14) crosses below threshold (e.g., 70 = overbought)|

**WebSocket flow:**
1. On app startup (market hours), connect `KiteTicker`
2. Subscribe to instrument tokens from all active alerts
3. On each tick, push to Redis pub/sub channel
4. Alert evaluator service consumes ticks, checks conditions
5. On trigger: mark alert as triggered, send Telegram notification, log event
6. One-shot alerts auto-deactivate after triggering; recurring alerts reset

**Technical indicators:**
- Compute RSI, SMA, EMA using tick history stored in Redis (rolling window)
- Use `pandas` or manual calculation — no heavy TA library needed for basic indicators

**Telegram integration:**
- Create a Telegram bot via BotFather
- Store chat_id in config
- On alert trigger: `bot.send_message(chat_id, formatted_alert_text)`
- Message format: `ALERT: RELIANCE crossed above 2,500.00 | LTP: 2,501.35 | Time: 14:23 IST`

**Frontend:**
- Alert builder: select symbol (autocomplete from instruments), condition type, threshold
- Active alerts table with toggle on/off
- Triggered alerts log

---

### Feature 4: Order Automation (with Risk Engine & Safety Layer)

**Kite API used:**
- `kite.place_order()` — place regular/bracket/cover orders
- `kite.modify_order()` — modify pending orders
- `kite.cancel_order()` — cancel pending orders
- `kite.order_margins()` — check margin requirement before placing
- `kite.margins()` — fetch available margin/equity

**Backend:**
- `POST /api/orders/place` — manual order placement (passes through risk engine)
- `DELETE /api/orders/{order_id}` — cancel order
- `PUT /api/orders/{order_id}` — modify order
- `POST /api/rules` — create automation rule
- `GET /api/rules` — list all rules
- `PUT /api/rules/{id}` — update rule
- `DELETE /api/rules/{id}` — deactivate rule
- `GET /api/risk/status` — current risk engine state (drawdown, exposure, blocks)
- `GET /api/risk/exposure` — real-time exposure breakdown
- `POST /api/risk/panic` — PANIC BUTTON: cancel all open orders + square off all positions
- `PUT /api/risk/config` — update risk thresholds

**Rule engine:**
- Rules stored in `order_rules` table with JSONB condition + action
- Evaluated against live ticks (same WebSocket feed as alerts)
- Condition types:
  - `price_drop_pct` — "if price drops X% from today's open"
  - `price_level` — "if price reaches X"
  - `time_based` — "at 9:20 AM, place order"
  - `stoploss_trailing` — "trail SL by X% from high"

**Risk Engine (every order MUST pass through this before execution):**

```
Order Request
     │
     ▼
┌─────────────────────────────────┐
│  1. Safety Layer Check          │
│     - Is panic mode active?     │──── BLOCK if yes
│     - Is kill switch on?        │
│     - Is cooldown active?       │
└──────────────┬──────────────────┘
               │ PASS
               ▼
┌─────────────────────────────────┐
│  2. Margin Validation           │
│     - kite.order_margins()      │──── BLOCK if insufficient
│     - Require 20% buffer        │
└──────────────┬──────────────────┘
               │ PASS
               ▼
┌─────────────────────────────────┐
│  3. Exposure Validation         │
│     - Max single order value    │──── BLOCK if exceeded
│     - Max total exposure        │
│     - Max per-sector exposure   │
└──────────────┬──────────────────┘
               │ PASS
               ▼
┌─────────────────────────────────┐
│  4. Daily Drawdown Check        │
│     - Today's realized P&L      │──── BLOCK if daily loss
│     - Max daily loss threshold  │     limit breached
└──────────────┬──────────────────┘
               │ PASS
               ▼
┌─────────────────────────────────┐
│  5. Rate Limit Check            │
│     - Max orders per day        │──── BLOCK if exceeded
│     - Cooldown between orders   │
└──────────────┬──────────────────┘
               │ PASS
               ▼
┌─────────────────────────────────┐
│  6. Duplicate Detection         │
│     - Same symbol + side        │──── BLOCK if duplicate
│       within last 30 seconds    │
└──────────────┬──────────────────┘
               │ PASS
               ▼
         Execute Order
               │
               ▼
         Audit Event Logged
```

**Risk engine is NOT bypassable. Even manual orders go through it.**

**Safety Layer:**

| Feature                  | Behavior                                                              |
|--------------------------|-----------------------------------------------------------------------|
| Panic Button             | Cancels ALL open orders + squares off ALL positions immediately       |
|                          | Sets `panic_mode=true` — blocks all new orders until manually reset   |
|                          | Logs `safety.panic` audit event, sends Telegram alert                 |
| Max Daily Loss           | If realized P&L drops below -₹X (configurable), blocks all new orders|
|                          | Auto-resets next trading day                                          |
| Cooldown After N Losses  | After N consecutive losses (default 3), blocks orders for M minutes   |
| Volatility Kill Switch   | If INDIA VIX > threshold (e.g., 25), blocks all automated orders      |
|                          | Manual orders still allowed with warning                              |
| Max Position Size        | Single position cannot exceed X% of total equity (default 20%)        |
| Trading Hours Gate       | Block orders outside 9:15 AM - 3:30 PM IST                           |

**Safety config (stored in Redis, hot-reloadable):**
```json
{
  "panic_mode": false,
  "max_daily_loss": 10000,
  "max_order_value": 50000,
  "max_orders_per_day": 10,
  "max_position_pct": 20,
  "loss_cooldown_count": 3,
  "loss_cooldown_minutes": 30,
  "vix_kill_threshold": 25,
  "dry_run": true
}
```

**Execution flow:**
1. Tick arrives via WebSocket
2. Rule engine evaluates all active rules against current tick
3. If condition met: pass order through risk engine pipeline
4. If risk engine approves: place order → log audit event → notify via Telegram
5. If risk engine blocks: log block reason as audit event → notify via Telegram
6. Mark rule as executed (one-shot) or keep active (recurring)

**Frontend:**
- Order form: symbol, exchange, qty, order type, product, price
- Margin preview before submission
- **Panic button**: prominent red button, requires confirmation dialog
- Risk status panel: current drawdown, exposure %, orders remaining today
- Rule builder: name, symbol, condition (dropdowns), action (order params)
- Active rules list with enable/disable toggle
- Risk config editor (thresholds)
- Execution log with risk-blocked entries highlighted

---

### Feature 5: Tax & Reporting

**Backend:**
- `GET /api/tax/summary?fy=2025-2026` — STCG + LTCG summary for financial year
- `GET /api/tax/lots?fy=2025-2026` — detailed tax lot breakdown
- `GET /api/tax/wash-sales?fy=2025-2026` — flagged wash sale transactions
- `GET /api/tax/report/download?fy=2025-2026&format=csv` — downloadable report

**STCG/LTCG logic (Indian tax rules, equity):**
- Holding period > 365 days = LTCG, else STCG
- LTCG on equity: 10% above 1L exemption (Section 112A) — for reference display
- STCG on equity: 15% (Section 111A) — for reference display
- F&O gains: treated as business income (non-speculative) — separate bucket

**Tax lot computation (FIFO method):**
1. For each tradingsymbol, sort all BUY trades by date (ascending)
2. For each SELL trade, match against oldest available BUY lots
3. Compute gain = (sell_price - buy_price) * quantity
4. Determine holding_period = sell_date - buy_date
5. Classify as STCG or LTCG
6. Store in `tax_lots` table

**Wash sale detection:**
- Indian tax law doesn't have a formal wash sale rule like the US
- But for personal tracking: flag if same stock is re-bought within 30 days of a loss sale
- Display as advisory, not a tax adjustment

**Intraday vs delivery separation:**
- Product = MIS or product = CNC with same-day buy+sell = intraday (speculative business income)
- Product = CNC with multi-day hold = delivery (capital gains)
- Product = NRML (F&O) = non-speculative business income

**Daily Tax Estimation (new):**
- Background task runs at 4:00 PM IST daily
- Computes running totals for current FY:
  - Realized STCG to date
  - Realized LTCG to date
  - Intraday (speculative) P&L to date
  - F&O (non-speculative business) P&L to date
- Estimates tax liability:
  - STCG: 15% of gains (Section 111A)
  - LTCG: 10% of gains above ₹1L exemption (Section 112A)
  - Intraday/F&O: at applicable slab rate (user-configurable slab)
- Stores snapshot in `risk_snapshots` table
- Shows "Estimated advance tax due this quarter" based on FY quarter boundaries

**Report output:**
- Summary: total STCG, total LTCG, total intraday P&L, total F&O P&L, estimated tax
- Detail: per-scrip breakdown with buy/sell dates, quantity, prices, gain, type
- CSV export compatible with CA-friendly formats

**Frontend:**
- FY selector dropdown
- Summary cards: STCG, LTCG, Intraday P&L, F&O P&L
- **Daily tax ticker**: running estimated liability for current FY
- **Quarterly advance tax reminder**: estimated amount due this quarter
- Tax lots table with filters by gain type, symbol
- Wash sale warnings (highlighted rows)
- Download CSV button

---

### Cross-Cutting: Audit Trail (Event Log)

Every meaningful state change in the system is recorded as an immutable event in the `audit_events` table. Events are append-only — never updated or deleted.

**What gets logged:**

| Event Type          | When                                              | Payload                                       |
|---------------------|---------------------------------------------------|-----------------------------------------------|
| `auth.login`        | User completes Kite OAuth                         | `{timestamp, ip}`                             |
| `auth.expired`      | Token expiry detected                             | `{timestamp}`                                 |
| `order.placed`      | Order sent to Kite                                | `{order_id, symbol, side, qty, price, source}` |
| `order.filled`      | Order execution confirmed                         | `{order_id, fill_price, fill_qty}`            |
| `order.rejected`    | Kite rejects order                                | `{order_id, reason}`                          |
| `order.cancelled`   | Order cancelled (manual or panic)                 | `{order_id, source}`                          |
| `risk.blocked`      | Risk engine blocks an order                       | `{order_params, block_reason, rule_id}`       |
| `safety.panic`      | Panic button activated                            | `{open_orders_cancelled, positions_squared}`  |
| `safety.drawdown`   | Daily drawdown limit hit                          | `{realized_pnl, threshold}`                  |
| `safety.cooldown`   | Loss cooldown activated                           | `{consecutive_losses, cooldown_minutes}`      |
| `rule.triggered`    | Automation rule condition met                     | `{rule_id, rule_name, tick_data}`             |
| `alert.fired`       | Alert condition triggered                         | `{alert_id, symbol, condition, ltp}`          |
| `sync.completed`    | Trade/holdings sync completed                     | `{type, records_synced}`                      |
| `behavior.detected` | Behavioral pattern flagged                        | `{flag_type, severity, trade_ids}`            |

**Backend:**
- `GET /api/audit/events` — paginated list with filters (event_type, date range, entity_id)
- `GET /api/audit/events/{id}` — single event detail
- Events are written via `audit_service.log(event_type, entity_type, entity_id, payload, source)`
- This is called internally by all services — never exposed as a write API

**Frontend:**
- Audit log page: filterable table with event type chips, timestamp, payload preview
- Expandable rows showing full JSON payload
- Timeline view option for a specific entity (e.g., "show all events for order X")

---

## 7. Kite Connect Auth Flow

```
User                    App                         Zerodha
 │                       │                             │
 │  GET /auth/login      │                             │
 │──────────────────────>│                             │
 │                       │  redirect to Kite login URL │
 │<──────────────────────│                             │
 │                       │                             │
 │  User logs in on Zerodha                            │
 │─────────────────────────────────────────────────────>
 │                       │                             │
 │  redirect to /auth/callback?request_token=xxx       │
 │<─────────────────────────────────────────────────────
 │                       │                             │
 │                       │  POST generate_session()    │
 │                       │─────────────────────────────>
 │                       │  access_token + public_token│
 │                       │<─────────────────────────────
 │                       │                             │
 │                       │  store in Redis (TTL=1 day) │
 │  session cookie set   │                             │
 │<──────────────────────│                             │
```

**Daily re-auth:**
- Access token expires at ~6:00 AM IST daily
- Option A: User manually logs in each morning via the UI
- Option B: Automate using `pyotp` TOTP if user provides their Zerodha TOTP secret — store encrypted in DB

---

## 8. Background Tasks (APScheduler)

| Task                   | Schedule              | Description                                              |
|------------------------|-----------------------|----------------------------------------------------------|
| `sync_instruments`     | 6:30 AM IST daily     | Download full instrument list from Kite                   |
| `start_ticker`         | 9:00 AM IST weekdays  | Connect WebSocket, subscribe alert instruments            |
| `stop_ticker`          | 3:35 PM IST weekdays  | Gracefully disconnect WebSocket                           |
| `sync_trades`          | 3:45 PM IST daily     | Import today's trades into DB                             |
| `sync_holdings`        | 3:50 PM IST daily     | Refresh holdings snapshot                                 |
| `compute_tax_lots`     | 4:00 PM IST daily     | Recompute tax lots for current FY                         |
| `daily_tax_estimate`   | 4:05 PM IST daily     | Compute running tax liability for current FY              |
| `behavior_scan`        | 4:10 PM IST daily     | Run behavioral detection rules on today's trades          |
| `correlation_update`   | 4:15 PM IST daily     | Recompute portfolio correlation matrix                    |
| `risk_snapshot`        | 4:20 PM IST daily     | Snapshot exposure, drawdown, risk blocks into risk table  |
| `weekly_alpha_scan`    | 6:00 PM IST Fridays   | Compute hidden alpha: best strategy+time combos           |

---

## 9. Configuration (.env)

```env
# Kite Connect
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret

# Database
DATABASE_URL=postgresql+asyncpg://kitetrader:password@localhost:5432/kitetrader

# Redis
REDIS_URL=redis://localhost:6379/0

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# App
APP_SECRET_KEY=random-secret-for-sessions
APP_ENV=development
LOG_LEVEL=INFO

# Safety & Risk Engine
DRY_RUN=true
MAX_ORDER_VALUE=50000
MAX_ORDERS_PER_DAY=10
MAX_DAILY_LOSS=10000
MAX_POSITION_PCT=20
LOSS_COOLDOWN_COUNT=3
LOSS_COOLDOWN_MINUTES=30
VIX_KILL_THRESHOLD=25

# Tax
DEFAULT_TAX_SLAB_PCT=30
```

---

## 10. Docker Compose (Local Dev)

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - db
      - redis
    volumes:
      - ./app:/app/app

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: kitetrader
      POSTGRES_PASSWORD: password
      POSTGRES_DB: kitetrader
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend/src:/app/src

volumes:
  pgdata:
```

---

## 11. Implementation Phases

### Phase 1 — Foundation + Audit Layer (Week 1)
1. Initialize Poetry project, configure Ruff, mypy, pytest
2. Set up FastAPI app skeleton with config, health check
3. Docker Compose with Postgres + Redis
4. Alembic setup + initial migration (all tables including audit_events, risk_snapshots, behavior_flags, sector_map)
5. Implement audit service (append-only event logging) — this goes in first because everything else emits events
6. Implement Kite auth flow (login redirect + callback + token storage) — log `auth.login` events
7. Instrument master sync task — log `sync.completed` events
8. Audit events API route (GET /api/audit/events)
9. Tests for audit service

### Phase 2 — Portfolio Risk Cockpit (Week 2)
1. Kite client wrapper (holdings, positions, orders, trades, margins, historical data)
2. Sector map: load NSE sector classification into `sector_map` table
3. Portfolio service: sync + P&L computation + sector allocation
4. Correlation service: pairwise correlation matrix using 90-day historical closes
5. Exposure engine: total exposure, directional bias, leverage, overnight risk
6. Risk snapshot background task
7. Portfolio + correlation + exposure API routes
8. React frontend: dashboard layout, holdings table, P&L cards, sector chart, exposure meter, correlation heatmap, concentration warning
9. Tests for portfolio service, correlation, exposure

### Phase 3 — Trade Journal + Behavioral Detection (Week 3)
1. Trade sync background task (auto-import from Kite)
2. Journal service: auto-import, CRUD, analytics queries
3. Behavioral detection engine: implement all 7 detection rules (revenge, overtrade, cut winners, average losers, FOMO, size spike, loss streak)
4. End-of-day behavior scan background task
5. Weekly hidden alpha scan task
6. Journal + behavior API routes
7. Frontend: journal list, entry form, analytics charts, behavior insights panel, weekly alpha card
8. Tests for journal service and each behavioral detection rule

### Phase 4 — Alerts & Screener (Week 4)
1. KiteTicker WebSocket manager (connect, reconnect with exponential backoff, subscribe)
2. Redis pub/sub for tick distribution
3. Alert evaluator service (price, volume, RSI conditions)
4. Telegram notification service
5. Alert API routes
6. Frontend: alert builder, active alerts, triggered log
7. Tests for alert evaluation logic and WebSocket reconnection

### Phase 5 — Risk Engine + Safety Layer + Order Automation (Week 5-6)
**Week 5 — Risk Engine & Safety:**
1. Risk engine service: 6-stage validation pipeline (safety check → margin → exposure → drawdown → rate limit → duplicate detection)
2. Safety service: panic button (cancel all + square off), max daily loss gate, loss cooldown, VIX kill switch, trading hours gate
3. Safety config in Redis (hot-reloadable without restart)
4. Risk + safety API routes (GET /risk/status, POST /risk/panic, PUT /risk/config)
5. Frontend: panic button with confirmation dialog, risk status panel, risk config editor
6. Tests for every risk engine stage and safety trigger

**Week 6 — Order Automation:**
1. Order placement service (all orders route through risk engine)
2. Rule engine: condition evaluation against live ticks
3. Order + rule API routes
4. Frontend: order form with margin preview, rule builder, execution log with risk-blocked entries highlighted
5. Tests for rule engine, end-to-end order flow (rule trigger → risk engine → placement)

### Phase 6 — Tax & Reporting with Daily Estimation (Week 7)
1. Tax lot computation (FIFO matching)
2. STCG/LTCG classification
3. Wash sale detection
4. Daily tax estimation background task
5. CSV report generation
6. Tax API routes
7. Frontend: tax summary, lot breakdown, daily tax ticker, quarterly advance tax reminder, download CSV
8. Tests for tax calculations and daily estimation

### Phase 7 — Integration & Hardening (Week 8)
1. Error handling: global exception handlers, structured error responses
2. Logging: structured JSON logs with correlation IDs
3. Kite API rate limiter: token bucket (3 req/sec) in client wrapper
4. WebSocket reliability: reconnect with backoff + stale tick detection + Telegram alert on disconnect
5. Idempotency: dedup key on order placement to prevent double execution
6. Audit log frontend: filterable table, entity timeline view
7. End-to-end manual testing across all features
8. README with setup instructions

---

## 12. Key Risks & Mitigations

| Risk                                    | Mitigation                                                              |
|-----------------------------------------|-------------------------------------------------------------------------|
| Daily token expiry breaks automation    | TOTP-based auto-login or clear "re-auth needed" notification            |
| Kite API rate limit (3 req/s)           | Token bucket rate limiter in client wrapper                             |
| WebSocket disconnection during market   | Auto-reconnect with exponential backoff + stale tick detection + alert  |
| Accidental real order placement         | 6-stage risk engine, `DRY_RUN=true` default, panic button              |
| Runaway automation losses               | Max daily loss gate, loss cooldown, VIX kill switch                     |
| Duplicate orders from race conditions   | Dedup key on order placement, 30-second same-symbol-side check          |
| Incorrect tax calculation               | FIFO unit tests with known scenarios, disclaimer in reports             |
| Behavioral detection false positives    | Severity levels (info/warning/critical), acknowledge-to-dismiss         |
| Kite API changes / deprecation          | Isolate all Kite calls behind service layer, easy to swap               |
| Audit log grows unbounded               | Partition by month, archive after 2 years, index on event_type + date   |

---

## 13. API Route Summary

```
Auth
  GET    /api/auth/login                    → redirect to Kite login
  GET    /api/auth/callback                 → handle Kite OAuth callback
  GET    /api/auth/status                   → check if session is valid

Portfolio (Risk Cockpit)
  GET    /api/portfolio/holdings            → current holdings with P&L
  GET    /api/portfolio/positions           → current positions
  GET    /api/portfolio/orders              → today's orders
  GET    /api/portfolio/summary             → aggregated portfolio metrics
  GET    /api/portfolio/allocation          → sector/segment breakdown
  GET    /api/portfolio/correlation         → pairwise correlation matrix + concentration warnings
  GET    /api/portfolio/exposure            → total exposure, leverage, directional bias
  POST   /api/portfolio/sync               → force re-sync from Kite

Journal (Behavior Analytics)
  GET    /api/journal/entries               → list entries (filters: date, strategy, outcome)
  GET    /api/journal/entries/{id}          → single entry
  POST   /api/journal/entries              → create entry
  PUT    /api/journal/entries/{id}          → update entry
  DELETE /api/journal/entries/{id}          → delete entry
  POST   /api/journal/import               → auto-import today's trades
  GET    /api/journal/analytics            → win rate, strategy performance
  GET    /api/journal/behavior             → detected behavioral flags
  PUT    /api/journal/behavior/{id}/ack    → acknowledge a behavioral flag
  GET    /api/journal/alpha                → hidden alpha: best strategy+time combos

Alerts
  GET    /api/alerts                        → list all alert rules
  POST   /api/alerts                        → create alert rule
  PUT    /api/alerts/{id}                   → update alert rule
  DELETE /api/alerts/{id}                   → deactivate alert rule
  GET    /api/alerts/triggered              → triggered alert history

Risk & Safety
  GET    /api/risk/status                   → current risk state (drawdown, exposure, blocks today)
  GET    /api/risk/exposure                 → real-time exposure breakdown
  PUT    /api/risk/config                   → update risk thresholds (hot-reload)
  POST   /api/risk/panic                    → PANIC: cancel all orders + square off positions
  POST   /api/risk/reset                    → reset panic mode / cooldown

Orders
  POST   /api/orders/place                  → place order (passes through risk engine)
  PUT    /api/orders/{id}                   → modify order
  DELETE /api/orders/{id}                   → cancel order

Rules
  GET    /api/rules                         → list automation rules
  POST   /api/rules                         → create rule
  PUT    /api/rules/{id}                    → update rule
  DELETE /api/rules/{id}                    → deactivate rule

Tax
  GET    /api/tax/summary                   → STCG/LTCG/intraday/F&O summary
  GET    /api/tax/daily                     → running daily tax liability estimate
  GET    /api/tax/lots                      → detailed tax lot list
  GET    /api/tax/wash-sales                → flagged wash sale transactions
  GET    /api/tax/report/download           → CSV export

Audit
  GET    /api/audit/events                  → paginated event log (filters: type, date, entity)
  GET    /api/audit/events/{id}             → single event detail
  GET    /api/audit/timeline/{entity_id}    → all events for a specific entity
```
