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
The scanner analyzes watchlist stocks using 12 technical indicators and generates BUY/SELL signals with entry, stop-loss, target, confidence score, and detailed rationale.

#### Technical Indicators

| Category | Indicators |
|----------|-----------|
| Momentum | RSI (14), Stochastic RSI (14, 3, 3), MACD (12/26/9) |
| Trend | EMA crossover (9/21), ADX (14) with +DI/-DI |
| Volatility | Bollinger Bands (20, 2σ), ATR (14) |
| Volume | VWAP, Volume SMA ratio (20-period) |
| Price Action | Support/Resistance (swing high/low), 52-week high/low proximity |
| Candlestick | Doji, Hammer, Inverted Hammer, Bullish/Bearish Engulfing |

#### Confluence Scoring
Each indicator condition contributes points to a raw score (max ~210). The score is normalized to 0-100% confidence. Signals below 40% confidence are discarded.

**BUY score contributions:**
- RSI oversold: +20, recovering: +10
- MACD bullish crossover: +20, histogram positive: +10
- EMA bullish crossover: +15, bullish trend: +5
- Price above VWAP: +10
- Near lower Bollinger Band: +15
- Volume spike: +10
- Near support: +15
- Breakout above resistance with volume: +20
- Near 52-week low: +5
- Strong bullish ADX trend: +15
- Stochastic RSI oversold: +10, bullish crossover: +10
- Hammer pattern: +10, Bullish engulfing: +15

#### Stop-Loss & Target
- **Stop-loss**: ATR-based (1.5× ATR), tightened by 30% when near support/resistance levels
- **Target**: 2:1 risk-reward ratio from entry

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
| Cache | Redis (session + token storage) |
| Frontend | React 18, TypeScript, Tailwind CSS, Vite |
| Indicators | `ta` (Technical Analysis library), `pandas`, `numpy` |
| Broker API | Kite Connect SDK (`kiteconnect`) |
| Infrastructure | Docker Compose (app, frontend/nginx, postgres, redis) |
| Testing | pytest + pytest-asyncio (118 tests) |
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
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000

### First Use

1. Open http://localhost:5173
2. Click "Login to Kite" — completes OAuth flow
3. Go to Dashboard — click "Sync Holdings" to import portfolio
4. Go to Scanner — click "Import from Holdings" to populate watchlist
5. Click "Run Scan" to generate signals

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
POST /api/scanner/scan            — Run scanner on watchlist
GET  /api/signals                 — List signals (filter: status, signal_type, tradingsymbol)
GET  /api/signals/{id}            — Signal detail with full indicator data
PUT  /api/signals/{id}            — Update status (executed/expired)
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
│   ├── main.py                # FastAPI application
│   ├── deps.py                # Dependency injection
│   ├── db/                    # Database session + base model
│   ├── kite/                  # Kite Connect auth + async client
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/               # Pydantic request/response schemas
│   ├── services/              # Business logic
│   │   ├── indicator.py       # Technical indicator computation (pure)
│   │   ├── scanner.py         # Signal scoring, SL/target, rationale
│   │   ├── watchlist.py       # Watchlist CRUD + holdings import
│   │   ├── portfolio.py       # Portfolio analytics
│   │   ├── risk.py            # Risk snapshots
│   │   ├── correlation.py     # Correlation matrix
│   │   ├── alert.py           # Alert evaluation
│   │   ├── trade.py           # Trade sync
│   │   └── audit.py           # Audit logging
│   ├── routers/               # FastAPI route handlers
│   └── tasks/                 # Background tasks (instrument sync)
├── tests/                     # 118 pytest tests
├── frontend/
│   └── src/
│       ├── pages/             # Dashboard, Scanner, Trades, Alerts
│       ├── components/        # Reusable UI components
│       ├── api/               # Axios API client
│       └── types/             # TypeScript interfaces
├── alembic/                   # Database migrations
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Notes

- **Kite Historical Data Add-on** is required for the scanner to fetch OHLCV candles. Without it, scans will return errors with "Insufficient permission". Subscribe at [developers.kite.trade](https://developers.kite.trade).
- **Kite sessions expire daily** — you need to re-login each trading day. The frontend detects this automatically and shows a login prompt.
- **Rate limiting** — Kite API allows ~3 requests/second. The scanner uses `asyncio.Semaphore(3)` to respect this limit.
