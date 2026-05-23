# Scanner — End-to-End Signal Generation Flow

## 1. High-Level Architecture

```mermaid
flowchart TB
    subgraph Trigger["Scan Triggers"]
        BG["Background Scanner Loop<br/>(every 1 hour)"]
        MANUAL["Manual Scan<br/>(POST /api/scanner/scan)"]
        RESCAN["Immediate Rescan<br/>(0 active signals detected)"]
    end

    subgraph DataSource["Data Source"]
        INDICES["app/data/indices.py<br/>get_all_unique_symbols()<br/>~353 unique (symbol, exchange) pairs"]
        WATCHLIST["DB: watchlist_items<br/>(user's custom symbols)"]
    end

    BG -->|"all index stocks"| INDICES
    MANUAL -->|"index tab"| INDICES
    MANUAL -->|"watchlist tab"| WATCHLIST
    RESCAN -->|"polls every 60s"| BG

    INDICES --> SCAN["ScannerService.scan_symbols()"]
    WATCHLIST --> SCAN

    SCAN --> EXPIRE["_expire_old_signals()<br/>expire signals older than 2 days"]
    EXPIRE --> PARALLEL["Process each symbol<br/>asyncio.gather + Semaphore"]
    PARALLEL --> PROCESS["_process_symbol()<br/>(per symbol)"]
    PROCESS --> PERSIST["_persist_signals()<br/>UPSERT to DB"]
    PERSIST --> REDIS["Store metadata in Redis<br/>scanner:last_scan<br/>scanner:status"]
    PERSIST --> DB[("PostgreSQL<br/>signals table")]

    style BG fill:#4f46e5,color:#fff
    style MANUAL fill:#059669,color:#fff
    style RESCAN fill:#d97706,color:#fff
    style DB fill:#1e40af,color:#fff
    style REDIS fill:#dc2626,color:#fff
```

## 2. Background Scanner Loop

```mermaid
flowchart TD
    START([App Startup — lifespan]) --> INIT["asyncio.create_task(<br/>background_scanner_loop)"]
    INIT --> SCAN_ALL["run_background_scan()"]
    SCAN_ALL --> GET_SYMS["get_all_unique_symbols()<br/>~353 deduplicated pairs<br/>from 20 index lists"]
    GET_SYMS --> CREATE_SVC["Create ScannerService<br/>Semaphore(5) for background"]
    CREATE_SVC --> CALL_SCAN["service.scan_symbols(<br/>all_symbols, '15minute')"]
    CALL_SCAN --> STORE_META["Store in Redis:<br/>last_scan, status,<br/>signals_generated, errors_count,<br/>duration_seconds"]

    STORE_META --> POLL_LOOP["Sleep 60s intervals"]
    POLL_LOOP --> CHECK{"Active signals<br/>in DB?"}
    CHECK -->|"Yes + elapsed < 3600s"| POLL_LOOP
    CHECK -->|"No active signals"| IMMEDIATE["Immediate rescan"]
    CHECK -->|"elapsed >= 3600s"| HOURLY["Hourly rescan"]
    IMMEDIATE --> SCAN_ALL
    HOURLY --> SCAN_ALL

    SHUTDOWN([App Shutdown]) --> CANCEL["scanner_task.cancel()"]

    style START fill:#4f46e5,color:#fff
    style SHUTDOWN fill:#dc2626,color:#fff
    style IMMEDIATE fill:#d97706,color:#fff
```

## 3. Per-Symbol Processing Pipeline

```mermaid
flowchart TD
    ENTRY["_process_symbol(tradingsymbol, exchange, timeframe)"]
    ENTRY --> SEMAPHORE["Acquire Semaphore<br/>(3 for manual, 5 for background)"]
    SEMAPHORE --> FETCH["_fetch_candles()"]

    subgraph YFinance["Market Data Fetch"]
        FETCH --> YF_SYMBOL["Map symbol:<br/>NSE → RELIANCE.NS<br/>BSE → RELIANCE.BO"]
        YF_SYMBOL --> YF_INTERVAL["Map interval:<br/>15minute → 15m<br/>day → 1d"]
        YF_INTERVAL --> YF_PERIOD["Select period:<br/>intraday → 7 days<br/>daily → 1 year"]
        YF_PERIOD --> YF_CALL["yfinance.Ticker.history()<br/>returns OHLCV DataFrame"]
    end

    YF_CALL --> TO_DF["_candles_to_dataframe()<br/>Convert to pandas DataFrame"]
    TO_DF --> CHECK_LEN{"len(df) >= 30?"}
    CHECK_LEN -->|"No"| SKIP_NULL["return None<br/>(skip symbol)"]
    CHECK_LEN -->|"Yes"| COMPUTE["IndicatorService.compute_all(df)"]

    subgraph Indicators["12 Technical Indicators"]
        direction TB
        COMPUTE --> RSI["RSI (14)<br/>value, oversold, overbought,<br/>recovering, dropping"]
        COMPUTE --> MACD["MACD (12/26/9)<br/>macd, signal, histogram,<br/>bullish/bearish crossover"]
        COMPUTE --> EMA["EMA (9/21)<br/>fast, slow,<br/>crossover, trend"]
        COMPUTE --> BB["Bollinger Bands (20,2)<br/>upper, middle, lower,<br/>near_lower, near_upper"]
        COMPUTE --> VWAP["VWAP<br/>value, price_above,<br/>price_below"]
        COMPUTE --> VOL["Volume (SMA 20)<br/>current, sma, ratio,<br/>spike (>=1.5x)"]
        COMPUTE --> ATR["ATR (14)<br/>value, pct"]
        COMPUTE --> ADX["ADX (14)<br/>value, +DI, -DI,<br/>strong_trend, bullish/bearish_di"]
        COMPUTE --> STOCH["Stochastic RSI (14)<br/>K, D, oversold, overbought,<br/>crossover"]
        COMPUTE --> CANDLE["Candlestick Patterns<br/>doji, hammer, inverted_hammer,<br/>bullish/bearish engulfing"]
        COMPUTE --> SR["Support & Resistance<br/>nearest_support/resistance,<br/>near_support/resistance"]
        COMPUTE --> W52["52-Week High/Low<br/>high, low,<br/>near_high, near_low"]
    end

    RSI & MACD & EMA & BB & VWAP & VOL & ATR & ADX & STOCH & CANDLE & SR & W52 --> SCORE["Score BUY & SELL"]

    style ENTRY fill:#4f46e5,color:#fff
    style SKIP_NULL fill:#9ca3af,color:#fff
    style Indicators fill:#f0fdf4,stroke:#059669
```

## 4. Signal Scoring — BUY vs SELL

```mermaid
flowchart TD
    INDICATORS["All 12 Indicators Computed"] --> BUY_SCORE["_score_buy()"]
    INDICATORS --> SELL_SCORE["_score_sell()"]

    subgraph BuyScoring["BUY Score (max 200 pts)"]
        direction TB
        B1["RSI oversold (<30) → +20"]
        B2["RSI recovering from oversold → +10"]
        B3["MACD bullish crossover → +20"]
        B4["MACD histogram positive → +10"]
        B5["EMA 9/21 bullish crossover → +15<br/>OR EMA bullish trend → +5"]
        B6["Price above VWAP → +10"]
        B7["Near lower Bollinger Band → +15"]
        B8["Volume spike (>=1.5x) → +10"]
        B9["Near support level → +15"]
        B10["Near resistance + volume spike<br/>(breakout) → +20"]
        B11["Near 52-week low → +5"]
        B12["Strong ADX + bullish DI → +15"]
        B13["Stoch RSI oversold (<20) → +10"]
        B14["Stoch RSI bullish crossover → +10"]
        B15["Hammer pattern → +10"]
        B16["Bullish engulfing → +15"]
    end

    subgraph SellScoring["SELL Score (max 200 pts)"]
        direction TB
        S1["RSI overbought (>70) → +20"]
        S2["RSI dropping from overbought → +10"]
        S3["MACD bearish crossover → +20"]
        S4["MACD histogram negative → +10"]
        S5["EMA 9/21 bearish crossover → +15<br/>OR EMA bearish trend → +5"]
        S6["Price below VWAP → +10"]
        S7["Near upper Bollinger Band → +15"]
        S8["Volume spike (>=1.5x) → +10"]
        S9["Near resistance level → +15"]
        S10["Near support + volume spike<br/>(breakdown) → +20"]
        S11["Near 52-week high → +5"]
        S12["Strong ADX + bearish DI → +15"]
        S13["Stoch RSI overbought (>80) → +10"]
        S14["Stoch RSI bearish crossover → +10"]
        S15["Inverted hammer → +10"]
        S16["Bearish engulfing → +15"]
    end

    BUY_SCORE --> BuyScoring
    SELL_SCORE --> SellScoring

    BuyScoring --> COMPARE{"BUY score >= SELL score<br/>AND score > 0?"}
    SellScoring --> COMPARE

    COMPARE -->|"BUY wins"| TYPE_BUY["signal_type = BUY<br/>raw_score = buy_score"]
    COMPARE -->|"SELL wins"| TYPE_SELL["signal_type = SELL<br/>raw_score = sell_score"]
    COMPARE -->|"Both 0"| SKIP["return None — no signal"]

    TYPE_BUY --> CONFIDENCE
    TYPE_SELL --> CONFIDENCE

    CONFIDENCE["confidence = (raw_score / 200) * 100<br/>capped at 100%"]
    CONFIDENCE --> THRESHOLD{"confidence >= 40%?"}
    THRESHOLD -->|"No"| SKIP2["return None — too weak"]
    THRESHOLD -->|"Yes"| SL_TARGET["Compute SL & Target"]

    style BuyScoring fill:#f0fdf4,stroke:#059669
    style SellScoring fill:#fef2f2,stroke:#dc2626
    style SKIP fill:#9ca3af,color:#fff
    style SKIP2 fill:#9ca3af,color:#fff
```

## 5. Stop Loss & Target Computation

```mermaid
flowchart TD
    ENTRY_PRICE["entry_price = last close"] --> SL_CALC

    subgraph SL_CALC["Stop Loss Calculation"]
        ATR_SL["Base SL distance =<br/>ATR x 1.5 multiplier"]
        ATR_SL --> SR_CHECK{"Near Support/Resistance?"}

        SR_CHECK -->|"BUY near support"| TIGHTEN_BUY["sr_distance = entry - support<br/>if sr_distance < sl_distance:<br/>sl_distance = sr_distance x 1.3"]
        SR_CHECK -->|"SELL near resistance"| TIGHTEN_SELL["sr_distance = resistance - entry<br/>if sr_distance < sl_distance:<br/>sl_distance = sr_distance x 1.3"]
        SR_CHECK -->|"No"| USE_ATR["Use ATR-based SL distance"]

        TIGHTEN_BUY --> APPLY_SL
        TIGHTEN_SELL --> APPLY_SL
        USE_ATR --> APPLY_SL

        APPLY_SL{"Signal Type?"}
        APPLY_SL -->|"BUY"| SL_BUY["SL = entry - sl_distance"]
        APPLY_SL -->|"SELL"| SL_SELL["SL = entry + sl_distance"]
    end

    SL_BUY --> TARGET
    SL_SELL --> TARGET

    subgraph TARGET["Target Calculation (RRR 2:1)"]
        RISK["risk = |entry - stop_loss|"]
        RISK --> REWARD["reward = risk x 2.0"]
        REWARD --> TARGET_CHECK{"Signal Type?"}
        TARGET_CHECK -->|"BUY"| T_BUY["target = entry + reward"]
        TARGET_CHECK -->|"SELL"| T_SELL["target = entry - reward"]
    end

    T_BUY --> SIGNAL_OBJ["Create Signal object"]
    T_SELL --> SIGNAL_OBJ

    style SL_CALC fill:#fef2f2,stroke:#dc2626
    style TARGET fill:#f0fdf4,stroke:#059669
```

## 6. Signal Persistence — Upsert & Dedup

```mermaid
flowchart TD
    RESULTS["scan_results:<br/>list of (ScanResultItem, Signal)"] --> LOOP["For each signal"]

    LOOP --> QUERY["SELECT FROM signals<br/>WHERE tradingsymbol = ?<br/>AND timeframe = ?<br/>AND status = 'active'"]

    QUERY --> EXISTS{"Existing active<br/>signal found?"}

    EXISTS -->|"Yes — UPSERT"| UPDATE["Update in-place:<br/>signal_type, entry_price,<br/>stop_loss, target_price,<br/>confidence, indicators,<br/>rationale, created_at = now()"]

    EXISTS -->|"No — INSERT"| INSERT["db.add(signal)<br/>New row with status='active'"]

    UPDATE --> NEXT["Next signal"]
    INSERT --> NEXT
    NEXT --> LOOP

    LOOP -->|"All done"| COMMIT["db.commit()<br/>Single transaction"]
    COMMIT --> DB[("PostgreSQL: signals table")]

    subgraph Expiry["Auto-Expiry (runs before each scan)"]
        EXP_QUERY["SELECT FROM signals<br/>WHERE status = 'active'<br/>AND created_at < now() - 2 days"]
        EXP_QUERY --> EXP_UPDATE["SET status = 'expired'<br/>SET expired_at = now()"]
        EXP_UPDATE --> EXP_COMMIT["db.commit()"]
    end

    style DB fill:#1e40af,color:#fff
    style UPDATE fill:#d97706,color:#fff
    style INSERT fill:#059669,color:#fff
    style Expiry fill:#fef2f2,stroke:#dc2626
```

## 7. Signal Lifecycle

```mermaid
stateDiagram-v2
    [*] --> active: Signal created<br/>(confidence >= 40%)

    active --> active: Upsert on rescan<br/>(same symbol+timeframe,<br/>refresh created_at)
    active --> executed: User marks as executed
    active --> expired: User manually expires
    active --> expired: Auto-expire (>2 days old)
    active --> expired: Expire All (bulk)

    executed --> [*]
    expired --> [*]

    note right of active
        Rescan upsert updates:
        signal_type, entry_price,
        stop_loss, target_price,
        confidence, indicators,
        rationale, created_at
    end note
```

## 8. Frontend Data Flow

```mermaid
flowchart LR
    subgraph IndexTab["Index Tab (e.g. Nifty 50)"]
        BADGE["Freshness badge:<br/>'Last scan: 23m ago'"]
        NO_BUTTON["No Run Scan button"]
    end

    subgraph WatchlistTab["Watchlist Tab"]
        SCAN_BTN["Run Scan button"]
        TIMEFRAME["Timeframe selector"]
    end

    STATUS_API["GET /api/scanner/status"]
    SIGNALS_API["GET /api/signals?status=active"]
    SCAN_API["POST /api/scanner/scan"]

    STATUS_API -->|"poll every 60s"| BADGE
    SIGNALS_API -->|"load on mount + tab switch"| TABLE["Signals Table"]
    SCAN_BTN -->|"manual trigger"| SCAN_API
    SCAN_API -->|"response"| TABLE

    subgraph Table["Signal Table Columns"]
        direction TB
        COL1["Symbol"]
        COL2["Type (BUY/SELL)"]
        COL3["Timeframe"]
        COL4["Entry Price"]
        COL5["Stop Loss"]
        COL6["Target Price"]
        COL7["Confidence (0-100%)"]
        COL8["Status"]
        COL9["Time (timeAgo)"]
        COL10["Actions"]
    end

    TABLE --> Table

    style IndexTab fill:#f0fdf4,stroke:#059669
    style WatchlistTab fill:#eff6ff,stroke:#3b82f6
```

## 9. Complete End-to-End Sequence

```mermaid
sequenceDiagram
    participant Loop as Background Loop
    participant Indices as indices.py
    participant Scanner as ScannerService
    participant Expiry as _expire_old_signals
    participant YF as yfinance
    participant Indicator as IndicatorService
    participant Scoring as _score_buy/_sell
    participant SL as _compute_stop_loss
    participant DB as PostgreSQL
    participant Redis as Redis

    Loop->>Indices: get_all_unique_symbols()
    Indices-->>Loop: ~353 (symbol, exchange) pairs

    Loop->>Scanner: scan_symbols(all_symbols, "15minute")

    Scanner->>Expiry: expire signals > 2 days old
    Expiry->>DB: UPDATE status='expired' WHERE created_at < cutoff
    Expiry-->>Scanner: done

    par For each symbol (Semaphore=5)
        Scanner->>YF: fetch OHLCV (7d, 15m interval)
        YF-->>Scanner: candles[]
        Scanner->>Scanner: _candles_to_dataframe()
        Scanner->>Indicator: compute_all(df)

        Note over Indicator: RSI, MACD, EMA, Bollinger,<br/>VWAP, Volume, ATR, ADX,<br/>Stoch RSI, Candlestick,<br/>Support/Resistance, 52-Week

        Indicator-->>Scanner: indicators dict

        Scanner->>Scoring: _score_buy(indicators)
        Scoring-->>Scanner: buy_score (0-200)
        Scanner->>Scoring: _score_sell(indicators)
        Scoring-->>Scanner: sell_score (0-200)

        Note over Scanner: Pick stronger signal<br/>confidence = (score/200)*100<br/>Skip if < 40%

        Scanner->>SL: _compute_stop_loss(entry, ATR, S/R)
        SL-->>Scanner: stop_loss
        Scanner->>Scanner: _compute_target(RRR 2:1)
        Scanner->>Scanner: _generate_rationale()
    end

    Scanner->>DB: UPSERT for each signal<br/>(match on symbol+timeframe+active)
    DB-->>Scanner: committed

    Scanner-->>Loop: (results, errors)

    Loop->>Redis: SET scanner:last_scan
    Loop->>Redis: HSET scanner:status

    loop Every 60s
        Loop->>DB: COUNT active signals
        alt 0 active signals
            Loop->>Loop: Break — immediate rescan
        else elapsed >= 3600s
            Loop->>Loop: Break — hourly rescan
        end
    end
```
