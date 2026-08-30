"""Unattended daily Kite web login for the capture pipeline — CAPTURE ONLY, OPT-IN.

PAPER TRADING ONLY. This module automates the same Zerodha web login a human performs so
that the 09:00 capture timer finds a fresh access token every morning (tokens die at the
06:00 IST daily flush — plan-doc loophole #8). It touches exactly three Kite *web* endpoints
(``/api/login``, ``/api/twofa``, the hosted ``/connect/login`` redirect chain) plus the one
broker REST endpoint broker.py already uses (``POST /session/token``, reused via
:func:`app.options.broker.exchange_request_token` — one exchange code path, not two). No
order-placement, modification or cancellation endpoint is referenced anywhere, and the
``kiteconnect`` SDK stays unimported (see app.options.broker's docstring; the audit lives in
tests/test_options_capture.py::test_no_order_write_api_is_referenced).

Two warnings, both load-bearing:

- **Zerodha discourages automated login.** ``/api/login`` and ``/api/twofa`` are the web
  app's own endpoints, not part of the published Kite Connect API; they can change without
  notice and automating them is against Zerodha's guidance. This runs against the user's own
  account, by the user's explicit decision (see deploy/RUNBOOK-capture.md). The manual
  ``/kite/login`` flow in app.options.broker remains the supported fallback.
- **Opt-in and inert by default.** The module does nothing until ``KITE_USER_ID``,
  ``KITE_PASSWORD`` and ``KITE_TOTP_SECRET`` are all present in the environment (same
  ``.env`` convention as broker.py). Absent any of them it exits 0 with one line saying so.
  Because the ``.env`` then holds full-account credentials, key-only SSH and ``chmod 600``
  on the file are mandatory — the runbook spells this out.

The password, the TOTP seed and every generated TOTP code are never logged, never printed
and never interpolated into any exception, mirroring broker.py's handling of the api_secret.
TOTP is RFC 6238 (SHA-1, 6 digits, 30 s) on stdlib hmac/struct/base64 — no new dependency.

Redirect handling is deliberately manual: the post-2FA ``GET /connect/login`` chain is
followed one ``Location`` at a time, only while it stays on kite.zerodha.com. The hop that
leaves Kite is the app's registered redirect (``http://127.0.0.1:.../kite/callback`` — a
loopback URL that resolves to nothing useful on the VPS); its ``request_token`` query
parameter is parsed out and that hop is **never requested**.

Failure exits are non-zero with one terse category for the systemd journal — ``login
rejected`` / ``twofa rejected`` / ``no request_token`` / ``exchange failed`` — and every
outcome writes a row to the same ``heartbeats`` table capture.py uses (loophole #15: a dead
auto-login must be distinguishable from a quiet one). Idempotent: if the stored token is
already fresh, it exits 0 without touching Kite.

Run (see deploy/options-autologin.service + .timer, 08:45 IST Mon-Fri)::

    python -m app.options.autologin [--token-db data/options/kite_token.db]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import os
import sqlite3
import struct
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from app.options import notify
from app.options.broker import (
    REQUEST_TIMEOUT_SECONDS,
    StoredToken,
    exchange_request_token,
    load_token,
    login_url,
    store_token,
)
from app.options.calendar import now_ist
from app.options.capture import DEFAULT_CAPTURE_DB, ensure_schema

# ── Endpoints and environment ────────────────────────────────────────────────────────────

#: Zerodha's web app host. The two /api endpoints below belong to the web app, NOT the
#: published Kite Connect REST API — they are undocumented and may change without notice.
KITE_WEB_HOST = "kite.zerodha.com"
KITE_WEB_BASE = f"https://{KITE_WEB_HOST}"
WEB_LOGIN_PATH = "/api/login"
WEB_TWOFA_PATH = "/api/twofa"

ENV_USER_ID = "KITE_USER_ID"
ENV_PASSWORD = "KITE_PASSWORD"
ENV_TOTP_SECRET = "KITE_TOTP_SECRET"

#: The /connect/login chain observed in practice is 2-3 hops (login -> finish -> redirect);
#: this bound only stops a pathological loop.
MAX_REDIRECT_HOPS = 8

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

#: RFC 6238 defaults; Zerodha's external-TOTP setup uses exactly these (SHA-1, 6, 30).
TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30

# ── Failure categories (terse, journal-friendly, credential-free) ────────────────────────

CATEGORY_LOGIN_REJECTED = "login rejected"
CATEGORY_TWOFA_REJECTED = "twofa rejected"
CATEGORY_NO_REQUEST_TOKEN = "no request_token"
CATEGORY_EXCHANGE_FAILED = "exchange failed"

EXIT_CODES = {
    CATEGORY_LOGIN_REJECTED: 2,
    CATEGORY_TWOFA_REJECTED: 3,
    CATEGORY_NO_REQUEST_TOKEN: 4,
    CATEGORY_EXCHANGE_FAILED: 5,
}


class AutoLoginError(RuntimeError):
    """One failed auto-login step. ``detail`` must never contain credential material."""

    def __init__(self, category: str, detail: str = "") -> None:
        self.category = category
        self.detail = detail
        self.exit_code = EXIT_CODES[category]
        super().__init__(f"{category}: {detail}" if detail else category)


# ── Credentials (never logged, never echoed) ─────────────────────────────────────────────


def _credential(name: str) -> str:
    # Never log, print, store or interpolate the returned value into any error message.
    return os.environ.get(name, "").strip()


def credentials_configured() -> bool:
    """True once the user has opted in by setting all three auto-login variables."""
    return all(_credential(name) for name in (ENV_USER_ID, ENV_PASSWORD, ENV_TOTP_SECRET))


# ── TOTP — RFC 6238 on stdlib only ───────────────────────────────────────────────────────


def _hotp(key: bytes, counter: int, digits: int) -> str:
    """RFC 4226 HOTP (SHA-1): dynamic truncation of HMAC(key, big-endian counter)."""
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF) % (10**digits)
    return f"{value:0{digits}d}"


def totp_code(
    secret: str, *, at: float | None = None, digits: int = TOTP_DIGITS, period: int = TOTP_PERIOD_SECONDS
) -> str:
    """The RFC 6238 TOTP code for ``secret`` (base32) at Unix time ``at`` (default: now).

    The returned code and the secret must never appear in logs or exceptions.
    """
    normalized = secret.replace(" ", "").rstrip("=").upper()
    try:
        key = base64.b32decode(normalized + "=" * (-len(normalized) % 8))
    except ValueError:
        # Deliberately from None and value-free: the secret must not leak via a traceback.
        raise RuntimeError(f"{ENV_TOTP_SECRET} is not valid base32 (value not shown)") from None
    moment = time.time() if at is None else at
    return _hotp(key, int(moment // period), digits)


# ── The web-login sequence ───────────────────────────────────────────────────────────────


async def _post_form(client: httpx.AsyncClient, path: str, form: dict[str, str]) -> tuple[int, Any]:
    response = await client.post(KITE_WEB_BASE + path, data=form)
    is_json = response.headers.get("content-type", "").startswith("application/json")
    return response.status_code, (response.json() if is_json else {})


def _rejection_detail(status_code: int, body: Any) -> str:
    # error_type is Kite's own classification; our inputs are never echoed back into it.
    return f"HTTP {status_code}, error_type={body.get('error_type', 'unknown')}"


async def web_login(client: httpx.AsyncClient) -> None:
    """POST /api/login then /api/twofa; on success the session cookies live in ``client``.

    Both endpoints are undocumented web-app internals (see module docstring). The observed
    contract: login returns ``{"status": "success", "data": {"request_id": ...}}``; twofa
    with ``twofa_type="totp"`` returns ``{"status": "success"}`` and sets session cookies.
    """
    user_id = _credential(ENV_USER_ID)
    status_code, body = await _post_form(
        client, WEB_LOGIN_PATH, {"user_id": user_id, "password": _credential(ENV_PASSWORD)}
    )
    if status_code != 200 or body.get("status") != "success":
        raise AutoLoginError(CATEGORY_LOGIN_REJECTED, _rejection_detail(status_code, body))
    request_id = str(body.get("data", {}).get("request_id", ""))
    if not request_id:
        raise AutoLoginError(CATEGORY_LOGIN_REJECTED, "login response carried no request_id")
    status_code, body = await _post_form(
        client,
        WEB_TWOFA_PATH,
        {
            "user_id": user_id,
            "request_id": request_id,
            "twofa_value": totp_code(_credential(ENV_TOTP_SECRET)),
            "twofa_type": "totp",
        },
    )
    if status_code != 200 or body.get("status") != "success":
        raise AutoLoginError(CATEGORY_TWOFA_REJECTED, _rejection_detail(status_code, body))


async def fetch_request_token(client: httpx.AsyncClient) -> str:
    """Walk the hosted /connect/login redirect chain manually and extract ``request_token``.

    Follows ``Location`` hops only while they stay on kite.zerodha.com. The hop that leaves
    Kite is the registered redirect (a 127.0.0.1 callback that is useless on the VPS): its
    query string is parsed for ``request_token`` and the hop itself is never requested.
    """
    url = httpx.URL(login_url())
    for _ in range(MAX_REDIRECT_HOPS):
        response = await client.get(url)  # client must not auto-follow redirects
        if response.status_code not in REDIRECT_STATUSES:
            raise AutoLoginError(
                CATEGORY_NO_REQUEST_TOKEN,
                f"HTTP {response.status_code} from {url.path} where a redirect was expected "
                "(session cookies not honoured?)",
            )
        next_url = url.join(response.headers.get("location", ""))
        request_token = next_url.params.get("request_token", "")
        if request_token:
            return str(request_token)
        if next_url.host != KITE_WEB_HOST:
            raise AutoLoginError(CATEGORY_NO_REQUEST_TOKEN, "redirect left kite.zerodha.com without a request_token")
        url = next_url
    raise AutoLoginError(CATEGORY_NO_REQUEST_TOKEN, f"no request_token within {MAX_REDIRECT_HOPS} redirect hops")


async def perform_autologin(*, token_db: Path | None = None, client: httpx.AsyncClient | None = None) -> StoredToken:
    """The full unattended sequence: web login -> request_token -> exchange -> store.

    The exchange and the store are broker.py's existing functions — capture.py reads the
    resulting token with no changes. Raises :class:`AutoLoginError` on any failed step.
    """
    own_client = client is None
    active = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)  # redirects NOT auto-followed (default)
    try:
        await web_login(active)
        request_token = await fetch_request_token(active)
        try:
            access_token = await exchange_request_token(request_token, client=active)
        except RuntimeError as exc:
            # broker.exchange_request_token's message is credential-free by construction.
            raise AutoLoginError(CATEGORY_EXCHANGE_FAILED, str(exc)) from None
    finally:
        if own_client:
            await active.aclose()
    return store_token(access_token, db=token_db)


# ── Heartbeats (same table capture.py writes — loophole #15) ─────────────────────────────


def write_heartbeat(db: Path, event: str, detail: str) -> None:
    """Append an ``autologin_*`` row to the capture DB's heartbeats table."""
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO heartbeats (ts, event, detail) VALUES (?, ?, ?)", (now_ist().isoformat(), event, detail)
        )
        conn.commit()
    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unattended daily Kite login for the capture pipeline (capture only, opt-in)"
    )
    parser.add_argument("--token-db", type=Path, default=None, help="SQLite file for the Kite access token")
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_CAPTURE_DB, help="SQLite file whose heartbeats table records the outcome"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if not credentials_configured():
        # Inert until the user opts in — and this must stay exit 0 so the timer unit is green.
        print(
            f"kite auto-login not configured ({ENV_USER_ID}/{ENV_PASSWORD}/{ENV_TOTP_SECRET} not all set); "
            "the manual /kite/login flow remains the path"
        )
        return 0
    stored = load_token(db=args.token_db)
    if stored is not None and stored.fresh():
        detail = f"token already fresh until {stored.expires_at.isoformat()}"
        write_heartbeat(args.db, "autologin_skipped", detail)
        print(f"kite auto-login skipped: {detail}")
        return 0
    try:
        stored = asyncio.run(perform_autologin(token_db=args.token_db))
    except AutoLoginError as exc:
        write_heartbeat(args.db, "autologin_error", str(exc))
        notify.send(
            f"❌ Kite auto-login failed: {exc.category} — manual fallback: /kite/login before 09:10",
            heartbeat_db=args.db,
        )
        print(f"kite auto-login failed: {exc.category}", file=sys.stderr)
        return exc.exit_code
    detail = f"token stored, expires {stored.expires_at.isoformat()}"
    write_heartbeat(args.db, "autologin_ok", detail)
    notify.send(f"✅ Kite login OK, token valid till {stored.expires_at.strftime('%H:%M')}", heartbeat_db=args.db)
    print(f"kite auto-login ok: {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
