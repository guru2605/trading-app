# Runbook — Phase 0b option-chain capture (1 GB Linode)

Capture only. `app/options/broker.py` and `app/options/capture.py` read quotes and write
SQLite; there is no order-placement code path anywhere in `app/options/` (grep-audited in
`tests/test_options_capture.py::test_no_order_write_api_is_referenced`).

## One-time setup

1. **Kite Connect app** (Rs 500/mo, developers.kite.trade). Set the redirect URL to
   `http://127.0.0.1:8756/kite/callback` (login is done through an SSH tunnel; the auth
   server never listens publicly).
2. **`.env` at the repo root** (never commit it):

   ```
   KITE_API_KEY=...
   KITE_API_SECRET=...
   ```

3. **Install units** (templates in this directory; fix the `EDITME` paths first):

   ```
   sudo cp deploy/options-capture.service deploy/options-capture.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now options-capture.timer
   ```

## Daily token login — manual flow (the default)

Kite access tokens die at the **06:00 IST daily flush** (plan-doc loophole #8). Before
09:15 IST on a capture day, from your laptop:

```
ssh -L 8756:127.0.0.1:8756 trader@<linode>
cd trading-app && .venv/bin/uvicorn --factory app.options.broker:create_auth_app \
    --port 8756 --env-file .env
```

Open <http://127.0.0.1:8756/kite/login>, complete the Zerodha login + TOTP; the callback
stores the token in `data/options/kite_token.db` and replies with `created_at`/`expires_at`
(it never echoes the token). Ctrl-C the uvicorn process — it is only needed for login.

If the token is missing or stale the capture service exits immediately with a loud
`RuntimeError` naming the expiry time; that failure is visible in `journalctl` and by the
**absence of a `start` heartbeat** in the capture DB.

## Unattended auto-login (opt-in — read the warnings first)

`app/options/autologin.py` automates the same web login so the 09:00 capture finds a fresh
token every morning without the SSH-tunnel ritual. Decide with eyes open:

- **Zerodha discourages automated login.** `/api/login` and `/api/twofa` are the web app's
  internal endpoints, not the published Kite Connect API; they can change without notice.
  This runs against your own account, by your own decision. If it breaks one morning, the
  manual flow above is the fallback — the auto-login timer fires at **08:45 IST** precisely
  so a failure leaves half an hour to log in by hand before the 09:15 window.
- **The `.env` then holds full-account credentials** (user ID, password, TOTP seed — enough
  to log in as you). Key-only SSH on the box (`PasswordAuthentication no`) and
  `chmod 600 .env` (owned by `trader`) are **mandatory**, not suggestions.
- The module is **inert until you opt in**: with any of the three variables missing it
  exits 0 with one line saying auto-login is not configured and the manual `/kite/login`
  flow remains the path. No code change needed to stay manual-only.

### One-time Zerodha step: get the plain-text TOTP seed

Kite's 2FA normally shows only a QR code. To automate you need the seed itself:

1. Kite web → profile → **Password & Security** → re-setup **External 2FA / TOTP**.
2. When the QR is shown, click the option to reveal the **plain-text secret** (a base32
   string). Copy it into `KITE_TOTP_SECRET`.
3. **Scan the same QR into your phone authenticator before finishing the setup**, so the
   phone and the VPS share one seed and both stay valid. Completing a *new* TOTP setup
   later invalidates the old seed — if you ever re-setup 2FA, update `KITE_TOTP_SECRET`.

### Enable

Append to the (600-perms) `.env`:

```
KITE_USER_ID=AB1234
KITE_PASSWORD=...
KITE_TOTP_SECRET=...   # base32 seed from the re-setup step above
```

Install the units (templates in this directory; fix the `EDITME` paths first):

```
sudo cp deploy/options-autologin.service deploy/options-autologin.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now options-autologin.timer
```

Dry-run once by hand: `.venv/bin/python -m app.options.autologin` (idempotent — if the
stored token is already fresh it exits 0 without touching Kite).

### How it behaves

- Timer fires **08:45 IST Mon–Fri** (`Persistent=true`; holidays are harmless, capture
  gates itself).
- Success prints `kite auto-login ok: token stored, expires ...` and writes an
  `autologin_ok` heartbeat to `data/options/capture.db`. It never prints the token or any
  credential.
- Failure exits non-zero with one terse category in the journal — `login rejected` (2),
  `twofa rejected` (3), `no request_token` (4), `exchange failed` (5) — plus an
  `autologin_error` heartbeat. On any of these, fall back to the manual flow above.
- Morning check: `journalctl -u options-autologin.service --since today` and the
  heartbeats query below (expect an `autologin_ok` or `autologin_skipped` row).

## What runs when

- If enabled, the auto-login timer fires **08:45 IST Mon–Fri** and refreshes the token
  (idempotent; see the section above).
- Capture timer fires **09:00 IST Mon–Fri** (`OnCalendar=Mon..Fri 09:00 Asia/Kolkata`).
- The process exits immediately on NSE holidays (`calendar.is_trading_day` — the
  holiday/weekend gate only; expiry days and DTE<5 days **are** captured: we would not trade
  them, but spreads and latency are worth measuring every session).
- It sleeps until **09:15**, snapshots every **5 s** (`SNAPSHOT_INTERVAL_SECONDS`) until
  **10:00**, writes an `end` heartbeat, and is gone by **10:05** (`CAPTURE_HARD_STOP`;
  systemd `RuntimeMaxSec` is a backstop only).
- Per cycle: one batched `/quote` for NIFTY 50, NIFTY BANK and INDIA VIX, then one for the
  chains — ATM±5 strikes × CE/PE × up to 2 eligible (DTE≥5) expiries × 2 indices ≈ 88
  instruments, far under Kite's 500-per-call and 1 req/s limits.

## Where the data lands

`data/options/capture.db` (gitignored):

- `chain_snapshots(ts, index_name, expiry, strike, opt_type, bid, ask, bid_qty, ask_qty,
  ltp, volume, oi, feed_ts)` — `feed_ts` is the exchange timestamp, kept for the §2.7
  staleness measurement. An empty book is stored as NULL bid/ask, not zero — that is the
  §2.5 no-quote signal.
- `index_snapshots(ts, symbol, ltp, feed_ts)` — spot + India VIX.
- `heartbeats(ts, event, detail)` — `start` / `cycle_error` / `end` / `skipped` from the
  capture, plus `autologin_ok` / `autologin_skipped` / `autologin_error` if auto-login is
  enabled. **Loophole #15:** a day with no heartbeat row at all means the pipeline is dead,
  not quiet.

## Morning-after checks (Phase 0b gate needs 10 clean sessions)

```
sqlite3 data/options/capture.db "SELECT * FROM heartbeats ORDER BY ts DESC LIMIT 5;"
sqlite3 data/options/capture.db "SELECT COUNT(*), MIN(ts), MAX(ts) FROM chain_snapshots
    WHERE ts >= date('now');"
journalctl -u options-capture.service --since today
```

Expect ~540 cycles (45 min / 5 s) and a `start` + `end` heartbeat pair. Anything else goes
in the day log before it is forgotten.
