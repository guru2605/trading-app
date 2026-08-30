"""Telegram push notifications for the capture pipeline — CAPTURE ONLY, OPT-IN, BEST-EFFORT.

PAPER TRADING ONLY. This module talks to exactly one non-broker service — the Telegram Bot
API (``sendMessage``, plus ``getUpdates`` once during setup) — so the daily auto-login and
capture status reach the user's phone without logging in anywhere. It references no Kite
endpoint at all, places no orders, and the ``kiteconnect`` SDK stays unimported (the
permanent audit in tests/test_options_capture.py::test_no_order_write_api_is_referenced
sweeps this file too).

Three properties, all load-bearing:

- **Inert until configured.** Without ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` in the
  environment (same ``.env`` convention as broker.py), :func:`send` is a no-op returning
  False with a single debug-level line — every caller works unchanged before the user sets
  up a bot.
- **Best-effort, never raises.** A notification failure must never break auto-login or
  capture: :func:`send` swallows every exception, returns False, logs one terse line and
  writes a ``notify_error`` heartbeat row (loophole #15: failures must be visible somewhere).
- **The bot token never leaks.** It is part of the request URL path
  (``/bot<TOKEN>/sendMessage``), and httpx exception messages embed full URLs — so every
  string derived from an exception is passed through :func:`_redact` before it reaches a log
  line or a heartbeat row. Message *text* is sent without ``parse_mode`` (plain text), so no
  Markdown-escaping landmines either.

CLI::

    python -m app.options.notify "message"          # ad-hoc send (exit 0 sent / 1 not)
    python -m app.options.notify --failure UNIT     # systemd OnFailure= hook (always exit 0)
    python -m app.options.notify --chat-id-probe    # one-time setup: print your chat_id

The ``--failure`` form backs ``deploy/options-notify-failure@.service``, which the capture
and auto-login units name in ``OnFailure=`` — that catches hard crashes (OOM kill, python
gone) that in-process notification cannot report.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from app.options.calendar import now_ist

logger = logging.getLogger(__name__)

# ── Endpoints and environment ────────────────────────────────────────────────────────────

TELEGRAM_API_BASE = "https://api.telegram.org"

ENV_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"
ENV_CHAT_ID = "TELEGRAM_CHAT_ID"

#: Short and non-negotiable: a slow Telegram must never hold up the capture window.
NOTIFY_TIMEOUT_SECONDS = 10.0

#: What a redacted bot token looks like in logs and heartbeat rows.
REDACTION_MARKER = "<bot-token-redacted>"


def _credential(name: str) -> str:
    # Never log, print, store or interpolate the returned value into any error message.
    return os.environ.get(name, "").strip()


def configured() -> bool:
    """True once the user has opted in by setting both Telegram variables."""
    return bool(_credential(ENV_BOT_TOKEN)) and bool(_credential(ENV_CHAT_ID))


def _redact(text: str, token: str) -> str:
    """Strip the bot token out of ``text`` — httpx exception messages embed the full URL."""
    return text.replace(token, REDACTION_MARKER) if token else text


# ── Failure heartbeat (same table capture.py writes — loophole #15) ──────────────────────


def _record_failure(heartbeat_db: Path | None, detail: str) -> None:
    """Log one terse line and append a ``notify_error`` heartbeat row. ``detail`` must
    already be redacted. Never raises — this runs inside the never-raises guarantee."""
    logger.warning("telegram notify failed: %s", detail)
    # Imported here, not at module top: capture.py imports this module, and this is the one
    # place notify needs anything from capture (the heartbeats DDL + default DB path).
    from app.options.capture import DEFAULT_CAPTURE_DB, ensure_schema

    db = heartbeat_db if heartbeat_db is not None else DEFAULT_CAPTURE_DB
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        try:
            ensure_schema(conn)
            conn.execute(
                "INSERT INTO heartbeats (ts, event, detail) VALUES (?, ?, ?)",
                (now_ist().isoformat(), "notify_error", detail),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:  # even the failure record is best-effort
        logger.warning("telegram notify heartbeat write failed: %s", exc)


# ── Sending ──────────────────────────────────────────────────────────────────────────────


def send(text: str, *, heartbeat_db: Path | None = None, client: httpx.Client | None = None) -> bool:
    """Push ``text`` to the configured Telegram chat. Best-effort: NEVER raises.

    Returns True only when Telegram confirmed delivery. Returns False when unconfigured
    (one debug line, nothing else) or on any failure (one terse redacted warning plus a
    ``notify_error`` heartbeat row). ``parse_mode`` is deliberately omitted — plain text,
    no Markdown-escaping surprises.
    """
    token = _credential(ENV_BOT_TOKEN)
    chat_id = _credential(ENV_CHAT_ID)
    if not token or not chat_id:
        logger.debug("telegram notify not configured (%s/%s not both set); message dropped", ENV_BOT_TOKEN, ENV_CHAT_ID)
        return False
    own_client = client is None
    active = client or httpx.Client(timeout=NOTIFY_TIMEOUT_SECONDS)
    try:
        response = active.post(f"{TELEGRAM_API_BASE}/bot{token}/sendMessage", data={"chat_id": chat_id, "text": text})
        body: Any = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.status_code != 200 or body.get("ok") is not True:
            _record_failure(
                heartbeat_db,
                f"sendMessage HTTP {response.status_code}, description={body.get('description', 'n/a')}",
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — deliberate: a notification must never break the caller
        _record_failure(heartbeat_db, _redact(f"sendMessage {type(exc).__name__}: {exc}", token))
        return False
    finally:
        if own_client:
            active.close()


# ── One-time setup: find your chat_id ────────────────────────────────────────────────────


def probe_chat_id(*, client: httpx.Client | None = None) -> int:
    """Call ``getUpdates`` and print the most recent sender's chat_id and first name.

    Prints exactly one line on success and nothing else to stdout (errors go to stderr).
    Used once during setup: message the bot from your phone, then run this.
    """
    token = _credential(ENV_BOT_TOKEN)
    if not token:
        print(f"{ENV_BOT_TOKEN} is not set; cannot probe", file=sys.stderr)
        return 1
    own_client = client is None
    active = client or httpx.Client(timeout=NOTIFY_TIMEOUT_SECONDS)
    try:
        response = active.get(f"{TELEGRAM_API_BASE}/bot{token}/getUpdates")
        payload: Any = response.json()
    except Exception as exc:  # noqa: BLE001 — same never-leak rule as send()
        print(f"getUpdates failed: {_redact(f'{type(exc).__name__}: {exc}', token)}", file=sys.stderr)
        return 1
    finally:
        if own_client:
            active.close()
    updates = payload.get("result", []) if payload.get("ok") is True else []
    for update in reversed(updates):
        message = update.get("message") or update.get("channel_post") or {}
        chat_id = message.get("chat", {}).get("id")
        if chat_id is not None:
            print(f"chat_id={chat_id} first_name={message.get('from', {}).get('first_name', '')}")
            return 0
    print("no messages found — send your bot any message first, then re-run", file=sys.stderr)
    return 1


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telegram push notifications for the capture pipeline (capture only, opt-in, best-effort)"
    )
    parser.add_argument("text", nargs="?", default=None, help="message to send")
    parser.add_argument("--failure", metavar="UNIT", default=None, help="notify that a systemd unit crashed")
    parser.add_argument("--chat-id-probe", action="store_true", help="print the chat_id of the bot's latest message")
    parser.add_argument(
        "--db", type=Path, default=None, help="SQLite file whose heartbeats table records notify failures"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.chat_id_probe:
        return probe_chat_id()
    if args.failure:
        # OnFailure= hook: always exit 0 — a crash notifier that itself fails a unit would
        # only add a second red unit to the journal without telling anyone anything.
        send(f"❌ {args.failure} crashed — check journalctl", heartbeat_db=args.db)
        return 0
    if args.text is None:
        print("nothing to do: pass a message, --failure UNIT, or --chat-id-probe", file=sys.stderr)
        return 2
    return 0 if send(args.text, heartbeat_db=args.db) else 1


if __name__ == "__main__":
    sys.exit(main())
