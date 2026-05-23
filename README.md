# Kite Trader

A self-hosted trading platform built on Zerodha's Kite Connect API. Portfolio tracking, risk analytics, trade journaling, alerts, and an intelligent intraday signal scanner — all in one app.

## Features

### Portfolio Management
- **Holdings sync** from Kite Connect with P&L tracking
- **Positions & Orders** — live view of intraday positions and order book
- **Portfolio summary** — total invested, current value, day P&L, overall P&L
- **Sector allocation** — pie chart breakdown by sector
- **Concentration risk** — warns when single-stock exposure exceeds thresholds

### Risk Analytics
- **Correlation matrix** — heatmap of holding correlations using historical returns
- **Exposure meter** — long/short/net exposure with sector breakdown
- **Risk snapshots** — periodic snapshots for trend analysis

### Scanner (Signal Generator)

The scanner runs a background scan every hour across ~561 Nifty 500 stocks on **two timeframes** (15-minute intraday and daily), computing BUY/SELL signals with entry, stop-loss, target, confidence score, and detailed rationale. Signals are deduplicated (same symbol + timeframe = upsert) and auto-expired after 2 days.

#### Signal Selection Pipeline

The scanner follows an 8-step pipeline to select and score signals:

**Step 1 — Market Context (fetched once per scan):**
- India VIX (`^INDIAVIX` via yfinance)
- Nifty 50 5-day return (`^NSEI` via yfinance)
- FII/DII net activity (NSE API)

**Step 2 — Per-Symbol Data Fetching (3 concurrent):**
- Intraday candles (15min, 7 days)
- Daily candles (1 year, for EMA 50/200 and MTF confirmation)
- Delivery volume % (NSE bhavcopy CSV)
- News sentiment (Google News RSS, top 5 headlines)

**Step 3 — Indicator Computation (12 core + 5 extended):**

| # | Indicator | Source | What it detects |
|---|-----------|--------|-----------------|
| 1 | RSI (14) | Intraday | Oversold (<30), overbought (>70), recovering/dropping |
| 2 | MACD (12/26/9) | Intraday | Bullish/bearish crossover, histogram direction |
| 3 | EMA (9/21) | Intraday | Crossover detection, trend direction |
| 4 | Bollinger Bands (20, 2σ) | Intraday | Near upper/lower band |
| 5 | VWAP | Intraday | Price above/below |
| 6 | Volume (SMA 20) | Intraday | Spike (>1.5x avg), trend (rising/falling/flat), acceleration, confirmation |
| 7 | ATR (14) | Intraday | Volatility measure (used for stop-loss) |
| 8 | ADX (14) | Intraday | Trend strength (>25), bullish/bearish DI |
| 9 | Stochastic RSI (14) | Intraday | Oversold/overbought, crossovers |
| 10 | Candlestick Patterns | Intraday | Doji, hammer, inverted hammer, bullish/bearish engulfing |
| 11 | Support/Resistance | Intraday | Nearest levels, proximity detection |
| 12 | 52-Week High/Low | Intraday | Proximity to annual extremes |
| 13 | EMA 50/200 | Daily | Strong uptrend/downtrend, golden/death cross |
| 14 | Relative Strength vs Nifty | Intraday+Benchmark | 5-day return comparison, outperformer/underperformer (>2% threshold) |
| 15 | Fibonacci Retracement | Intraday | 38.2%, 50%, 61.8% levels from recent swing high/low |
| 16 | Delivery Volume % | NSE | Institutional vs speculative activity |
| 17 | News Sentiment | Google News RSS | Positive/negative keyword scoring from headlines |

**Step 4 — Scoring (BUY and SELL scored independently):**

Both directions are scored independently. The stronger direction is picked.

*Primary indicators (trigger confluence bonus):*

| Factor | Points |
|--------|--------|
| RSI oversold / overbought | 30 |
| RSI recovering / dropping | 15 |
| MACD crossover | 30 |
| EMA 9/21 crossover | 22 |

*Secondary indicators:*

| Factor | Points |
|--------|--------|
| EMA 50/200 trend aligned | +20 |
| EMA 50/200 counter-trend | -15 |
| MACD histogram direction | 10 |
| EMA 9/21 trend (no crossover) | 8 |
| VWAP alignment | 10 |
| Bollinger near band | 15 |
| Volume spike | 10 |
| Volume trend rising + confirmed | +10 |
| Volume trend falling | -5 |
| Near support / resistance | 15 |
| Breakout / breakdown with volume | 20 |
| ADX strong + directional DI | 15 |
| Stochastic RSI oversold / overbought | 10 |
| Stochastic RSI crossover | 10 |
| Relative strength aligned | +15 |
| Relative strength counter | -10 |
| Fibonacci near level | 10 |
| Delivery >60% | +15 |
| Delivery <30% | -10 |
| Sentiment aligned | +10 |
| Sentiment counter | -5 |
| FII/DII flow aligned | 5 |

*Tertiary indicators:*

| Factor | Points |
|--------|--------|
| 52-week near extreme | 3 |
| Hammer / inverted hammer | 7 |
| Engulfing pattern | 10 |

*Confluence bonus:*

| Condition | Bonus |
|-----------|-------|
| 3 of 4 primary indicators agree | +25 |
| All 4 primary indicators agree | +40 |

Max theoretical score: 357 pts.

**Step 5 — Signal Selection:**
```
Pick stronger direction: max(buy_score, sell_score)
Confidence = (raw_score / 380) × 100%
Filter: confidence < 40% → discard
```

**Step 6 — Post-Scoring Multipliers (applied sequentially):**

| Multiplier | Condition | Effect |
|------------|-----------|--------|
| MTF Confirmation | Daily RSI+MACD+EMA agree with signal | × 1.20 |
| MTF Confirmation | Daily indicators disagree | × 0.85 |
| VIX Filter | VIX > 25, BUY signal | × 0.85 |
| VIX Filter | VIX > 25, SELL signal | × 1.10 |
| VIX Filter | VIX < 13, BUY signal | × 0.90 |
| VIX Filter | VIX < 13, SELL signal | × 1.05 |
| Earnings Proximity | Earnings within 3 days | × 0.80 |
| Final cap | Always | min(confidence, 100%) |
| Threshold | confidence < 40% after multipliers | discard |

**Step 7 — Stop-Loss & Target:**
- **Stop-loss**: ATR × 1.5, tightened 30% when near support/resistance
- **Target**: 2:1 risk-reward ratio from entry

**Step 8 — Persist & Lifecycle:**
- Upsert: same symbol + timeframe → update existing active signal
- Auto-expire: signals older than 2 days
- Rescan: every 1 hour across both timeframes (immediate rescan if all signals expire)

#### Frontend Tabs
- **Top 10** — highest confidence signals across all stocks (default view), with **Export PDF** button
- **All Signals** — every signal with symbol search filter
- **Index tabs** — pre-computed data per index (no manual "Run Scan")
- **Watchlist** — manual "Run Scan" for user's custom symbols
- **Timeframe filter** — filter signals by "Intraday 15m" or "Daily"
- **Freshness badge** — shows time since last scan

#### PDF Export
- One-click **Export PDF** on the Top 10 tab downloads a PDF with signal details (symbol, type, entry/SL/target, confidence, timeframe) and full rationale for each signal

#### Watchlist Management
- **Import from Holdings** — one-click import of all portfolio holdings into scanner watchlist
- **Instrument search** — autocomplete search across 143K+ instruments for easy symbol discovery
- **Manual add/remove** — add any NSE/BSE symbol with optional notes

### Trade Sync & Journaling
- Automatic trade sync from Kite order book
- Trade history with filters

### Alerts
- Price-based, P&L-based, and allocation-based alert rules
- Configurable thresholds

### Auth
- Kite Connect OAuth login flow
- Redis-backed session management
- Frontend auto-detects expired sessions with login prompt

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Pydantic v2 |
| Database | PostgreSQL (via asyncpg) |
| Cache | Redis (session + token storage + scanner status) |
| Frontend | React 18, TypeScript, Tailwind CSS, Vite |
| Indicators | `ta` (Technical Analysis library), `pandas`, `numpy` |
| Market Data | `yfinance` (OHLCV, VIX, Nifty benchmark, earnings calendar) |
| External Data | NSE bhavcopy (delivery volume), Google News RSS (sentiment), NSE API (FII/DII) |
| Broker API | Kite Connect SDK (`kiteconnect`) |
| Infrastructure | Docker Compose (app, frontend/nginx, postgres, redis) |
| Testing | pytest + pytest-asyncio (240 tests) |
| Linting | Ruff (format + lint), mypy (type checking) |

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Kite Connect API key ([developers.kite.trade](https://developers.kite.trade))
- Kite Connect Historical Data Add-on (for scanner)

### Setup

```bash
# Clone
git clone https://github.com/guru2605/trading-app.git
cd trading-app

# Configure
cp .env.example .env
# Edit .env with your Kite API key and secret

# Start
docker compose up -d

# Run migrations
docker compose exec app alembic upgrade head
```

The app will be available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

### First Use

1. Open http://localhost:3000
2. Click "Login to Kite" — completes OAuth flow
3. Go to Dashboard — click "Sync Holdings" to import portfolio
4. Go to Scanner — signals are pre-computed automatically every hour
5. Use "Top 10" tab for highest-confidence signals, or search in "All Signals"

## API Endpoints

### Auth
```
GET  /api/auth/login          — Redirect to Kite login
GET  /api/auth/callback       — OAuth callback
GET  /api/auth/status         — Check session status
POST /api/auth/logout         — Clear session
```

### Portfolio
```
GET  /api/portfolio/holdings      — List holdings
GET  /api/portfolio/positions     — Live positions
GET  /api/portfolio/orders        — Order book
GET  /api/portfolio/summary       — Portfolio summary
GET  /api/portfolio/allocation    — Sector allocation
GET  /api/portfolio/correlation   — Correlation matrix
GET  /api/portfolio/exposure      — Exposure breakdown
POST /api/portfolio/sync          — Sync holdings from Kite
POST /api/portfolio/sync-instruments — Sync instrument master
```

### Scanner
```
POST /api/scanner/scan            — Run scanner on watchlist (manual)
GET  /api/scanner/status          — Background scanner status (last scan time, count, duration)
GET  /api/signals                 — List signals (filter: status, signal_type, tradingsymbol, timeframe)
GET  /api/signals/{id}            — Signal detail with full indicator data
PUT  /api/signals/{id}            — Update status (executed/expired)
POST /api/signals/expire-all      — Expire all active signals
```

### Watchlist
```
GET    /api/watchlist                      — List watchlist
POST   /api/watchlist                      — Add symbol
DELETE /api/watchlist/{id}                 — Remove symbol
POST   /api/watchlist/import-holdings      — Import from portfolio holdings
GET    /api/watchlist/search-instruments   — Search instruments (autocomplete)
```

### Alerts
```
GET    /api/alerts           — List alert rules
POST   /api/alerts           — Create alert rule
PUT    /api/alerts/{id}      — Update alert
DELETE /api/alerts/{id}      — Delete alert
POST   /api/alerts/evaluate  — Evaluate all active alerts
```

### Trades
```
GET  /api/trades             — List trades
POST /api/trades/sync        — Sync trades from Kite
```

### Audit
```
GET /api/audit               — Audit event log
```

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Lint + format
poetry run ruff format .
poetry run ruff check .

# Type check
poetry run mypy .

# All checks (format, style, types, tests)
./tasks.sh -fstu
```

## Project Structure

```
├── app/
│   ├── config.py              # Settings from environment
│   ├── main.py                # FastAPI application + background scanner lifespan
│   ├── deps.py                # Dependency injection
│   ├── db/                    # Database session + base model
│   ├── data/
│   │   └── indices.py         # 21 NSE index lists (561 unique Nifty 500 symbols)
│   ├── kite/                  # Kite Connect auth + async client
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/               # Pydantic request/response schemas
│   ├── services/
│   │   ├── indicator.py       # 17 technical indicators (pure computation)
│   │   ├── scanner.py         # Signal scoring, SL/target, rationale, MTF/VIX/earnings filters
│   │   ├── market_data.py     # yfinance: candles, VIX, Nifty benchmark, earnings calendar
│   │   ├── nse_data.py        # NSE: delivery volume (bhavcopy), FII/DII activity
│   │   ├── sentiment.py       # Google News RSS sentiment analysis
│   │   ├── watchlist.py       # Watchlist CRUD + holdings import
│   │   ├── portfolio.py       # Portfolio analytics
│   │   ├── risk.py            # Risk snapshots
│   │   ├── correlation.py     # Correlation matrix
│   │   ├── alert.py           # Alert evaluation
│   │   ├── trade.py           # Trade sync
│   │   └── audit.py           # Audit logging
│   ├── routers/               # FastAPI route handlers
│   └── tasks/
│       └── background_scanner.py  # Hourly background scan with immediate rescan
├── tests/                     # 240 pytest tests
├── frontend/
│   └── src/
│       ├── pages/             # Dashboard, Scanner, Trades, Alerts
│       ├── components/        # Reusable UI components
│       ├── api/               # Axios API client + scanner status
│       ├── data/              # Index lists, Top 10 / All Signals tabs
│       ├── utils/             # timeAgo helper
│       └── types/             # TypeScript interfaces
├── docs/
│   └── scanner-flow.md        # 9 Mermaid diagrams of end-to-end scanner flow
├── alembic/                   # Database migrations
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Notes

- **Background scanner** runs automatically every hour on two timeframes (15-minute and daily). No manual "Run Scan" needed for index stocks. Watchlist tab still supports manual scanning.
- **Kite Historical Data Add-on** is required for the scanner to fetch OHLCV candles. Without it, scans will return errors with "Insufficient permission". Subscribe at [developers.kite.trade](https://developers.kite.trade).
- **Kite sessions expire daily** — you need to re-login each trading day. The frontend detects this automatically and shows a login prompt.
- **Rate limiting** — yfinance is used for market data. The scanner uses `asyncio.Semaphore(3)` to limit concurrency.
- **NSE data** — delivery volume and FII/DII data depend on NSE availability. Data may be unavailable outside market hours or on holidays.
