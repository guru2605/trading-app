"""Tests for app.options.notify — best-effort Telegram push for the capture pipeline.

No network: every Telegram interaction goes through ``httpx.MockTransport``. The two
properties tested hardest are the never-raises guarantee (a notification failure must not
break auto-login or capture) and token secrecy — the bot token is part of the request URL,
httpx exception messages embed full URLs, and none of that may reach a log line, a
heartbeat row, or stdout.
"""

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

import app.options.autologin as autologin
import app.options.capture as capture
import app.options.notify as notify
from app.options.broker import StoredToken, store_token
from app.options.calendar import now_ist
from app.options.notify import (
    ENV_BOT_TOKEN,
    ENV_CHAT_ID,
    REDACTION_MARKER,
    TELEGRAM_API_BASE,
    configured,
    main,
    probe_chat_id,
    send,
)
from tests.test_options_capture import FORBIDDEN_SOURCE_STRINGS

FAKE_TOKEN = "123456:telegram-fake-bot-token-abc"  # noqa: S105 — test fixture, not a credential
FAKE_CHAT_ID = "987654321"


@pytest.fixture
def telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_BOT_TOKEN, FAKE_TOKEN)
    monkeypatch.setenv(ENV_CHAT_ID, FAKE_CHAT_ID)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _heartbeats(db: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db)
    try:
        return list(conn.execute("SELECT event, detail FROM heartbeats ORDER BY ts"))
    finally:
        conn.close()


# ── Opt-in gating (inert without env) ────────────────────────────────────────────────────


def test_configured_requires_both_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_BOT_TOKEN, raising=False)
    monkeypatch.delenv(ENV_CHAT_ID, raising=False)
    assert configured() is False
    monkeypatch.setenv(ENV_BOT_TOKEN, FAKE_TOKEN)
    assert configured() is False  # chat id still missing
    monkeypatch.setenv(ENV_CHAT_ID, FAKE_CHAT_ID)
    assert configured() is True


def test_unconfigured_send_is_a_noop_returning_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(ENV_BOT_TOKEN, raising=False)
    monkeypatch.delenv(ENV_CHAT_ID, raising=False)
    heartbeat_db = tmp_path / "capture.db"
    with caplog.at_level(logging.DEBUG, logger="app.options.notify"):
        assert send("hello", heartbeat_db=heartbeat_db) is False
    assert "not configured" in caplog.text
    assert not heartbeat_db.exists()  # inert means inert: no heartbeat, no file


# ── Sending (MockTransport — no network) ─────────────────────────────────────────────────


def test_send_posts_plain_text_to_the_bot_url(telegram_env: None) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.telegram.org"
        assert request.url.path == f"/bot{FAKE_TOKEN}/sendMessage"
        seen.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    with _client(handler) as client:
        assert send("✅ all good", client=client) is True
    assert seen["chat_id"] == FAKE_CHAT_ID
    assert seen["text"] == "✅ all good"
    assert "parse_mode" not in seen  # plain text: no Markdown-escaping landmines


def test_send_http_failure_returns_false_and_writes_a_heartbeat(telegram_env: None, tmp_path: Path) -> None:
    heartbeat_db = tmp_path / "capture.db"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with _client(handler) as client:
        assert send("hello", heartbeat_db=heartbeat_db, client=client) is False
    events = _heartbeats(heartbeat_db)
    assert len(events) == 1
    assert events[0][0] == "notify_error"
    assert "chat not found" in events[0][1]
    assert FAKE_TOKEN not in events[0][1]


def test_send_treats_ok_false_as_failure_even_with_http_200(telegram_env: None, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "flood control"})

    with _client(handler) as client:
        assert send("hello", heartbeat_db=tmp_path / "capture.db", client=client) is False


def test_send_timeout_never_raises(telegram_env: None, tmp_path: Path) -> None:
    heartbeat_db = tmp_path / "capture.db"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    with _client(handler) as client:
        assert send("hello", heartbeat_db=heartbeat_db, client=client) is False  # no exception escapes
    assert _heartbeats(heartbeat_db)[0][0] == "notify_error"


def test_send_never_raises_even_on_unexpected_exceptions(telegram_env: None, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("completely unexpected")

    with _client(handler) as client:
        assert send("hello", heartbeat_db=tmp_path / "capture.db", client=client) is False


# ── Token secrecy (the token is IN the URL; httpx errors embed URLs) ─────────────────────


def test_connect_error_with_url_in_message_is_redacted_everywhere(
    telegram_env: None, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    heartbeat_db = tmp_path / "capture.db"
    url_bearing_message = f"[Errno -2] Name or service not known for {TELEGRAM_API_BASE}/bot{FAKE_TOKEN}/sendMessage"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(url_bearing_message, request=request)

    with caplog.at_level(logging.DEBUG, logger="app.options.notify"), _client(handler) as client:
        assert send("hello", heartbeat_db=heartbeat_db, client=client) is False
    detail = _heartbeats(heartbeat_db)[0][1]
    assert FAKE_TOKEN not in detail
    assert REDACTION_MARKER in detail
    assert FAKE_TOKEN not in caplog.text
    assert REDACTION_MARKER in caplog.text


def test_generic_exception_carrying_the_token_is_redacted(telegram_env: None, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"boom while talking to /bot{FAKE_TOKEN}/sendMessage")

    heartbeat_db = tmp_path / "capture.db"
    with _client(handler) as client:
        assert send("hello", heartbeat_db=heartbeat_db, client=client) is False
    assert FAKE_TOKEN not in _heartbeats(heartbeat_db)[0][1]


# ── chat_id probe ────────────────────────────────────────────────────────────────────────


def test_probe_prints_the_latest_chat_id_and_first_name_only(
    telegram_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/bot{FAKE_TOKEN}/getUpdates"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": [
                    {"update_id": 1, "message": {"chat": {"id": 111}, "from": {"first_name": "Old"}}},
                    {"update_id": 2, "message": {"chat": {"id": 424242}, "from": {"first_name": "Guru"}}},
                ],
            },
        )

    with _client(handler) as client:
        assert probe_chat_id(client=client) == 0
    out = capsys.readouterr().out
    assert out == "chat_id=424242 first_name=Guru\n"  # one line, nothing else
    assert FAKE_TOKEN not in out


def test_probe_with_no_updates_hints_and_fails(telegram_env: None, capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": []})

    with _client(handler) as client:
        assert probe_chat_id(client=client) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "send your bot any message first" in captured.err


def test_probe_without_a_token_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(ENV_BOT_TOKEN, raising=False)
    assert probe_chat_id() == 1
    assert ENV_BOT_TOKEN in capsys.readouterr().err


def test_probe_network_error_redacts_the_token(telegram_env: None, capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {TELEGRAM_API_BASE}/bot{FAKE_TOKEN}/getUpdates", request=request)

    with _client(handler) as client:
        assert probe_chat_id(client=client) == 1
    err = capsys.readouterr().err
    assert FAKE_TOKEN not in err
    assert REDACTION_MARKER in err


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def _record_sends(monkeypatch: pytest.MonkeyPatch, *, result: bool = True) -> list[str]:
    calls: list[str] = []

    def fake_send(text: str, *, heartbeat_db: Path | None = None, client: httpx.Client | None = None) -> bool:
        calls.append(text)
        return result

    monkeypatch.setattr(notify, "send", fake_send)
    return calls


def test_cli_adhoc_send_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record_sends(monkeypatch, result=True)
    assert main(["hello from the linode"]) == 0
    assert calls == ["hello from the linode"]
    _record_sends(monkeypatch, result=False)
    assert main(["hello again"]) == 1  # non-zero so setup problems are visible interactively


def test_cli_failure_mode_message_and_always_exit_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record_sends(monkeypatch, result=False)  # even a failed send must not fail the unit
    assert main(["--failure", "options-capture.service"]) == 0
    assert calls == ["❌ options-capture.service crashed — check journalctl"]


def test_cli_probe_flag_dispatches_to_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notify, "probe_chat_id", lambda: 0)
    assert main(["--chat-id-probe"]) == 0


def test_cli_with_nothing_to_do_exits_2(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _record_sends(monkeypatch)
    assert main([]) == 2
    assert "nothing to do" in capsys.readouterr().err


# ── Wiring: autologin.main notifies at its exit points ───────────────────────────────────


@pytest.fixture
def autologin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(autologin.ENV_USER_ID, "AB1234")
    monkeypatch.setenv(autologin.ENV_PASSWORD, "correct-horse-battery")
    monkeypatch.setenv(autologin.ENV_TOTP_SECRET, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")


def test_autologin_success_sends_the_ok_message(
    autologin_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_sends(monkeypatch)
    stored = StoredToken(access_token="secret-access-value-xyz", created_at=now_ist())

    async def fake_perform(*, token_db: Path | None = None, client: httpx.AsyncClient | None = None) -> StoredToken:
        return stored

    monkeypatch.setattr(autologin, "perform_autologin", fake_perform)
    assert autologin.main(["--token-db", str(tmp_path / "t.db"), "--db", str(tmp_path / "c.db")]) == 0
    assert calls == [f"✅ Kite login OK, token valid till {stored.expires_at.strftime('%H:%M')}"]
    assert "secret-access-value-xyz" not in calls[0]  # message carries the expiry, never the token


def test_autologin_failure_sends_the_category_and_fallback(
    autologin_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_sends(monkeypatch)

    async def fake_perform(*, token_db: Path | None = None, client: httpx.AsyncClient | None = None) -> StoredToken:
        raise autologin.AutoLoginError(autologin.CATEGORY_TWOFA_REJECTED, "HTTP 403, error_type=TwoFAException")

    monkeypatch.setattr(autologin, "perform_autologin", fake_perform)
    assert autologin.main(["--token-db", str(tmp_path / "t.db"), "--db", str(tmp_path / "c.db")]) == 3
    assert calls == ["❌ Kite auto-login failed: twofa rejected — manual fallback: /kite/login before 09:10"]


def test_autologin_idempotent_skip_is_silent(
    autologin_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_sends(monkeypatch)
    token_db = tmp_path / "t.db"
    store_token("fresh-token", db=token_db)  # created now -> fresh
    assert autologin.main(["--token-db", str(token_db), "--db", str(tmp_path / "c.db")]) == 0
    assert calls == []  # skip means silence, per spec


# ── Wiring: capture notifies start/done/fatal ────────────────────────────────────────────


def test_capture_fatal_error_sends_a_terse_reason_and_reraises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record_sends(monkeypatch)

    async def doomed(db: Path, token_db: Path | None = None) -> int:
        raise RuntimeError("Kite access token is STALE")

    monkeypatch.setattr(capture, "run_capture", doomed)
    with pytest.raises(RuntimeError, match="STALE"):
        capture.main(["--db", str(tmp_path / "c.db")])
    assert len(calls) == 1
    assert calls[0].startswith("❌ Capture failed: RuntimeError: Kite access token is STALE")


def test_capture_wires_start_and_done_notifications_at_the_exit_points() -> None:
    # run_capture cannot run hermetically in a unit test (it sleeps to the 09:15 IST window),
    # so pin the wiring at source level: both messages exist and skipped days stay silent.
    source = Path(capture.__file__).read_text()
    assert source.count("notify.send") == 3  # start, done, fatal — and nothing per-cycle
    assert "▶️ Capture started" in source
    assert "✔️ Capture done" in source
    assert source.index('"skipped"') < source.index("notify.send"), "non-trading-day exit must precede any send"


def test_expiry_summary_lists_both_indices() -> None:
    from datetime import date

    from app.options.contracts import Index

    expiries = {Index.NIFTY: [date(2026, 9, 8), date(2026, 9, 15)], Index.BANKNIFTY: []}
    assert capture._expiry_summary(expiries) == "NIFTY 2026-09-08, 2026-09-15; BANKNIFTY none"


# ── Capture-only constraint audit (extends test_options_capture's permanent sweep) ───────


def test_notify_is_covered_by_the_order_write_audit() -> None:
    source = Path(notify.__file__).read_text()
    for forbidden in FORBIDDEN_SOURCE_STRINGS:
        assert forbidden not in source, f"notify.py references forbidden API string {forbidden!r}"
    assert "api.kite.trade" not in source  # notify talks to Telegram only, never the broker
    assert "kite.zerodha.com" not in source


def test_send_default_heartbeat_db_is_the_capture_db(
    telegram_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The lazy capture import inside _record_failure must resolve and honour DEFAULT_CAPTURE_DB.
    default_db = tmp_path / "default-capture.db"
    monkeypatch.setattr(capture, "DEFAULT_CAPTURE_DB", default_db)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False, "description": "server error"})

    with _client(handler) as client:
        assert send("hello", client=client) is False
    assert _heartbeats(default_db)[0][0] == "notify_error"
