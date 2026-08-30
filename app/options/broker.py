"""Kite Connect authentication for the Phase 0b capture pipeline — CAPTURE ONLY.

PAPER TRADING ONLY. This module talks to exactly one write-nothing broker endpoint —
``POST /session/token``, the OAuth-style request-token exchange — plus the hosted login
redirect. No order-placement, modification or cancellation endpoint is referenced anywhere in
this package, and the official Kite SDK is deliberately NOT imported here: its client object
exposes the order-write methods this project bans, so using raw ``httpx`` against the read
endpoints keeps every broker write API not merely unused but unimportable from
``app.options``. (``httpx`` is already a project dependency; the token exchange is one POST
with a SHA-256 checksum, per https://kite.trade/docs/connect/v3/user/.) The strict source
audit lives in tests/test_options_capture.py::test_no_order_write_api_is_referenced.

Credentials come from the environment (``KITE_API_KEY`` / ``KITE_API_SECRET``; the repo-root
``.env`` can be loaded with ``uvicorn --env-file .env`` or systemd ``EnvironmentFile=``).
The secret is never logged, never stored, and never echoed in an error message.

Token lifecycle (source: Kite Connect v3 docs, "the access token ... expires at 6 AM the
next day"): a token obtained after 06:00 IST is valid until 06:00 IST the next day; the
daily flush also kills any token that predates the most recent 06:00. Freshness is computed
against that boundary and surfaced explicitly, because a stale token is loophole #8 of the
plan doc — a silently-dead unattended capture.

Run the login flow locally or on the VPS::

    uvicorn --factory app.options.broker:create_auth_app --port 8756 --env-file .env
    # open http://127.0.0.1:8756/kite/login and complete the Zerodha login;
    # the callback stores the access token in the token DB with its timestamp.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from app.options.calendar import IST, now_ist, to_ist

# ── Endpoints and environment ────────────────────────────────────────────────────────────

#: Kite Connect v3 hosted login. Source: https://kite.trade/docs/connect/v3/user/
KITE_LOGIN_URL_TEMPLATE = "https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"

#: REST base for the two read endpoints this package uses (session/token here; instruments
#: and quote in app.options.capture).
KITE_API_BASE = "https://api.kite.trade"
KITE_TOKEN_ENDPOINT = "/session/token"

#: Kite requires this header on every REST call. Source: Kite Connect v3 docs.
KITE_VERSION_HEADER = {"X-Kite-Version": "3"}

ENV_API_KEY = "KITE_API_KEY"
ENV_API_SECRET = "KITE_API_SECRET"

#: Access tokens die at the daily flush. Source: Kite Connect v3 docs ("expires at 6 AM the
#: next day"). Hour is in IST, like everything else in this package.
TOKEN_EXPIRY_HOUR = 6

#: Single-row token store. Lives under data/ (gitignored — see .gitignore).
#: Stdlib sqlite3, not aiosqlite: aiosqlite is only in the dev dependency group, this store
#: is hit twice a day, and a dependency the deploy target may not have is a worse trade than
#: a millisecond of blocking.
DEFAULT_TOKEN_DB = Path("data/options/kite_token.db")

REQUEST_TIMEOUT_SECONDS = 30.0


def api_key() -> str:
    """The Kite Connect api_key from the environment. Public identifier, safe to embed in URLs."""
    value = os.environ.get(ENV_API_KEY, "").strip()
    if not value:
        raise RuntimeError(f"{ENV_API_KEY} is not set; export it (e.g. uvicorn --env-file .env)")
    return value


def _api_secret() -> str:
    # Never log, print, store or interpolate the returned value into any error message.
    value = os.environ.get(ENV_API_SECRET, "").strip()
    if not value:
        raise RuntimeError(f"{ENV_API_SECRET} is not set; export it (e.g. uvicorn --env-file .env)")
    return value


# ── Login and token exchange ─────────────────────────────────────────────────────────────


def login_url() -> str:
    """The hosted Zerodha login URL for this app."""
    return KITE_LOGIN_URL_TEMPLATE.format(api_key=api_key())


def compute_checksum(key: str, request_token: str, secret: str) -> str:
    """SHA-256 of api_key + request_token + api_secret, hex-encoded.

    This is the exact recipe from the Kite Connect v3 docs for ``POST /session/token``.
    """
    return hashlib.sha256(f"{key}{request_token}{secret}".encode()).hexdigest()


async def exchange_request_token(request_token: str, *, client: httpx.AsyncClient | None = None) -> str:
    """Exchange the post-login ``request_token`` for an access token.

    Returns the access token string. Raises ``RuntimeError`` on failure with Kite's status
    and error type only — never with any credential material.
    """
    key = api_key()
    payload = {
        "api_key": key,
        "request_token": request_token,
        "checksum": compute_checksum(key, request_token, _api_secret()),
    }
    own_client = client is None
    active = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        response = await active.post(KITE_API_BASE + KITE_TOKEN_ENDPOINT, data=payload, headers=KITE_VERSION_HEADER)
    finally:
        if own_client:
            await active.aclose()
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code != 200 or body.get("status") != "success":
        # Deliberately terse: Kite's error_type/message are safe, our inputs are not echoed.
        raise RuntimeError(
            f"Kite token exchange failed: HTTP {response.status_code}, "
            f"error_type={body.get('error_type', 'unknown')}, message={body.get('message', 'n/a')}"
        )
    token = body.get("data", {}).get("access_token", "")
    if not token:
        raise RuntimeError("Kite token exchange returned success without an access_token")
    return str(token)


# ── Token freshness ──────────────────────────────────────────────────────────────────────


def token_expiry(created_at: datetime) -> datetime:
    """The first daily 06:00 IST flush strictly after ``created_at``.

    A token created at 07:00 lives until 06:00 the next day; a token created at 01:00 dies at
    06:00 the same morning. Naive datetimes are rejected by :func:`to_ist`.
    """
    created = to_ist(created_at)
    boundary = created.replace(hour=TOKEN_EXPIRY_HOUR, minute=0, second=0, microsecond=0)
    if created.time() >= time(TOKEN_EXPIRY_HOUR, 0):
        boundary += timedelta(days=1)
    return boundary


def is_fresh(created_at: datetime, now: datetime | None = None) -> bool:
    """True while the token created at ``created_at`` is still valid."""
    moment = to_ist(now) if now is not None else now_ist()
    return moment < token_expiry(created_at)


@dataclass(frozen=True)
class StoredToken:
    access_token: str
    created_at: datetime

    @property
    def expires_at(self) -> datetime:
        return token_expiry(self.created_at)

    def fresh(self, now: datetime | None = None) -> bool:
        return is_fresh(self.created_at, now)


# ── SQLite token store ───────────────────────────────────────────────────────────────────

_TOKEN_DDL = """
CREATE TABLE IF NOT EXISTS kite_token (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def store_token(access_token: str, *, db: Path | None = None, now: datetime | None = None) -> StoredToken:
    """Persist the day's access token (single-row upsert) with its IST creation time."""
    db = db if db is not None else DEFAULT_TOKEN_DB
    created = to_ist(now) if now is not None else now_ist()
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute(_TOKEN_DDL)
        conn.execute(
            "INSERT INTO kite_token (id, access_token, created_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET access_token = excluded.access_token, created_at = excluded.created_at",
            (access_token, created.isoformat()),
        )
    return StoredToken(access_token=access_token, created_at=created)


def load_token(*, db: Path | None = None) -> StoredToken | None:
    """The stored token, or None if the login flow has never been run."""
    db = db if db is not None else DEFAULT_TOKEN_DB
    if not db.exists():
        return None
    with sqlite3.connect(db) as conn:
        conn.execute(_TOKEN_DDL)
        row = conn.execute("SELECT access_token, created_at FROM kite_token WHERE id = 1").fetchone()
    if row is None:
        return None
    return StoredToken(access_token=row[0], created_at=datetime.fromisoformat(row[1]).astimezone(IST))


def require_fresh_token(*, db: Path | None = None, now: datetime | None = None) -> StoredToken:
    """The stored token, or a loud, actionable failure if it is missing or stale."""
    db = db if db is not None else DEFAULT_TOKEN_DB
    stored = load_token(db=db)
    if stored is None:
        raise RuntimeError(f"No Kite access token stored in {db}; run the /kite/login flow first")
    if not stored.fresh(now):
        raise RuntimeError(
            f"Kite access token is STALE (created {stored.created_at.isoformat()}, "
            f"expired {stored.expires_at.isoformat()}); re-run the /kite/login flow. "
            "Tokens die at the 06:00 IST daily flush — this is plan-doc loophole #8."
        )
    return stored


# ── FastAPI auth flow ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/kite", tags=["kite-auth"])


@router.get("/login")
async def kite_login() -> RedirectResponse:
    """Redirect to the hosted Zerodha login for this app."""
    return RedirectResponse(login_url())


@router.get("/callback")
async def kite_callback(request_token: str = "", status: str = "") -> dict[str, str | bool]:
    """Kite's post-login redirect target: exchange the request token and store the result.

    The response confirms storage and freshness only; it never contains the token itself.
    """
    if status and status != "success":
        raise HTTPException(status_code=400, detail=f"Kite login did not succeed (status={status})")
    if not request_token:
        raise HTTPException(status_code=400, detail="Missing request_token in Kite callback")
    access_token = await exchange_request_token(request_token)
    stored = store_token(access_token)
    return {
        "stored": True,
        "created_at": stored.created_at.isoformat(),
        "expires_at": stored.expires_at.isoformat(),
    }


def create_auth_app() -> FastAPI:
    """A standalone app for the login flow, so nothing in the existing app/ needs modifying.

    Run: ``uvicorn --factory app.options.broker:create_auth_app --port 8756 --env-file .env``
    """
    auth_app = FastAPI(title="Kite Connect auth (capture-only)", docs_url=None, redoc_url=None)
    auth_app.include_router(router)
    return auth_app
