"""Tests for app.options.autologin — unattended daily Kite web login (capture only).

No test here touches the network: the whole login sequence (web login, twofa, redirect
chain, token exchange) is exercised through ``httpx.MockTransport``. Secrecy assertions
mirror tests/test_options_broker.py: the password, the TOTP seed and every generated TOTP
code must never surface in exceptions, printed output or heartbeat rows.
"""

import base64
import sqlite3
from datetime import datetime
from pathlib import Path

import httpx
import pytest

import app.options.autologin as autologin
from app.options.autologin import (
    CATEGORY_EXCHANGE_FAILED,
    CATEGORY_LOGIN_REJECTED,
    CATEGORY_NO_REQUEST_TOKEN,
    CATEGORY_TWOFA_REJECTED,
    ENV_PASSWORD,
    ENV_TOTP_SECRET,
    ENV_USER_ID,
    AutoLoginError,
    credentials_configured,
    fetch_request_token,
    main,
    perform_autologin,
    totp_code,
)
from app.options.broker import ENV_API_KEY, ENV_API_SECRET, StoredToken, load_token, store_token
from app.options.calendar import IST
from tests.test_options_capture import FORBIDDEN_SOURCE_STRINGS

FAKE_KEY = "testkey123"
FAKE_SECRET = "testsecret456"
FAKE_USER_ID = "AB1234"
FAKE_PASSWORD = "correct-horse-battery"
#: base32 of the ASCII seed "12345678901234567890" — also the RFC 6238 test-vector key.
FAKE_TOTP_SECRET = base64.b32encode(b"12345678901234567890").decode()

REGISTERED_REDIRECT = "http://127.0.0.1:8756/kite/callback"


@pytest.fixture
def autologin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(ENV_API_SECRET, FAKE_SECRET)
    monkeypatch.setenv(ENV_USER_ID, FAKE_USER_ID)
    monkeypatch.setenv(ENV_PASSWORD, FAKE_PASSWORD)
    monkeypatch.setenv(ENV_TOTP_SECRET, FAKE_TOTP_SECRET)


def _form(request: httpx.Request) -> dict[str, str]:
    return dict(httpx.QueryParams(request.content.decode()))


def _json(status_code: int, payload: dict[str, object], extra_headers: dict[str, str] | None = None) -> httpx.Response:
    headers = {"content-type": "application/json", **(extra_headers or {})}
    return httpx.Response(status_code, json=payload, headers=headers)


class KiteStub:
    """A MockTransport handler for the whole login sequence, with per-step failure knobs."""

    def __init__(
        self,
        *,
        reject_login: bool = False,
        reject_twofa: bool = False,
        omit_request_token: bool = False,
        reject_exchange: bool = False,
        serve_login_page: bool = False,
    ) -> None:
        self.reject_login = reject_login
        self.reject_twofa = reject_twofa
        self.omit_request_token = omit_request_token
        self.reject_exchange = reject_exchange
        self.serve_login_page = serve_login_page
        self.seen_forms: dict[str, dict[str, str]] = {}
        self.requested_urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requested_urls.append(str(request.url))
        assert request.url.host != "127.0.0.1", "the localhost callback hop must never be requested"
        if request.url.host == "kite.zerodha.com":
            return self._web(request)
        if request.url.host == "api.kite.trade":
            return self._exchange(request)
        raise AssertionError(f"unexpected host {request.url.host}")

    def _web(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/login":
            self.seen_forms["login"] = _form(request)
            if self.reject_login:
                return _json(403, {"status": "error", "error_type": "GeneralException"})
            return _json(200, {"status": "success", "data": {"request_id": "req-id-1"}})
        if path == "/api/twofa":
            self.seen_forms["twofa"] = _form(request)
            if self.reject_twofa:
                return _json(403, {"status": "error", "error_type": "TwoFAException"})
            return _json(200, {"status": "success"}, extra_headers={"set-cookie": "kf_session=sess-cookie; Path=/"})
        if path == "/connect/login":
            if self.serve_login_page:
                return httpx.Response(200, text="<html>login form</html>")
            return httpx.Response(302, headers={"location": "/connect/finish?api_key=" + FAKE_KEY})
        if path == "/connect/finish":
            if self.omit_request_token:
                return httpx.Response(302, headers={"location": f"{REGISTERED_REDIRECT}?action=login&status=success"})
            return httpx.Response(
                302,
                headers={"location": f"{REGISTERED_REDIRECT}?request_token=rt-777&action=login&status=success"},
            )
        raise AssertionError(f"unexpected web path {path}")

    def _exchange(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/session/token"
        self.seen_forms["exchange"] = _form(request)
        if self.reject_exchange:
            return _json(403, {"status": "error", "error_type": "TokenException", "message": "bad checksum"})
        return _json(200, {"status": "success", "data": {"access_token": "fresh-access-token"}})


def _client(stub: KiteStub) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(stub))


# ── Opt-in gating ────────────────────────────────────────────────────────────────────────


def test_not_configured_until_all_three_variables_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (ENV_USER_ID, ENV_PASSWORD, ENV_TOTP_SECRET):
        monkeypatch.delenv(name, raising=False)
    assert credentials_configured() is False
    monkeypatch.setenv(ENV_USER_ID, FAKE_USER_ID)
    monkeypatch.setenv(ENV_PASSWORD, FAKE_PASSWORD)
    assert credentials_configured() is False  # TOTP seed still missing
    monkeypatch.setenv(ENV_TOTP_SECRET, FAKE_TOTP_SECRET)
    assert credentials_configured() is True


def test_unconfigured_main_exits_zero_inert(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in (ENV_USER_ID, ENV_PASSWORD, ENV_TOTP_SECRET):
        monkeypatch.delenv(name, raising=False)
    heartbeat_db = tmp_path / "capture.db"
    assert main(["--token-db", str(tmp_path / "kite_token.db"), "--db", str(heartbeat_db)]) == 0
    out = capsys.readouterr().out
    assert "not configured" in out
    assert "/kite/login" in out  # points at the manual fallback
    assert not heartbeat_db.exists()  # inert means inert: nothing written anywhere


# ── TOTP — RFC 6238 Appendix B test vectors (SHA-1) ──────────────────────────────────────


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_totp_matches_rfc_6238_appendix_b(at: int, expected: str) -> None:
    assert totp_code(FAKE_TOTP_SECRET, at=at, digits=8) == expected


def test_totp_default_is_six_digits_and_stable_within_a_period() -> None:
    code = totp_code(FAKE_TOTP_SECRET, at=59)
    assert len(code) == 6
    assert code == "94287082"[-6:]  # 6-digit code is the truncation of the 8-digit vector
    assert totp_code(FAKE_TOTP_SECRET, at=30) == totp_code(FAKE_TOTP_SECRET, at=59)  # same 30 s window
    assert totp_code(FAKE_TOTP_SECRET, at=60) != totp_code(FAKE_TOTP_SECRET, at=59)


def test_totp_accepts_spaced_lowercase_unpadded_seeds() -> None:
    relaxed = FAKE_TOTP_SECRET.lower().rstrip("=")
    spaced = " ".join([relaxed[:4], relaxed[4:]])
    assert totp_code(spaced, at=59, digits=8) == "94287082"


def test_totp_rejects_a_malformed_seed_without_echoing_it() -> None:
    with pytest.raises(RuntimeError, match=ENV_TOTP_SECRET) as excinfo:
        totp_code("not!base32@@", at=59)
    assert "not!base32@@" not in str(excinfo.value)


# ── Success path (MockTransport — no network) ────────────────────────────────────────────


async def test_success_path_stores_the_token_via_brokers_exchange(autologin_env: None, tmp_path: Path) -> None:
    db = tmp_path / "kite_token.db"
    stub = KiteStub()
    async with _client(stub) as client:
        stored = await perform_autologin(token_db=db, client=client)
    assert stored.access_token == "fresh-access-token"
    loaded = load_token(db=db)  # capture.py's require_fresh_token reads exactly this store
    assert loaded is not None
    assert loaded.access_token == "fresh-access-token"
    # The web login posted the documented forms...
    assert stub.seen_forms["login"]["user_id"] == FAKE_USER_ID
    assert stub.seen_forms["twofa"]["twofa_type"] == "totp"
    assert stub.seen_forms["twofa"]["request_id"] == "req-id-1"
    assert stub.seen_forms["twofa"]["twofa_value"] == totp_code(FAKE_TOTP_SECRET)
    # ...and the exchange went through broker.py's one code path (api_key + checksum form).
    assert stub.seen_forms["exchange"]["api_key"] == FAKE_KEY
    assert stub.seen_forms["exchange"]["request_token"] == "rt-777"
    # The registered-redirect hop was parsed, never fetched (KiteStub also asserts per call).
    assert all("127.0.0.1" not in url for url in stub.requested_urls)


async def test_twofa_session_cookie_is_carried_into_the_connect_flow(autologin_env: None, tmp_path: Path) -> None:
    stub = KiteStub()
    async with _client(stub) as client:
        await perform_autologin(token_db=tmp_path / "kite_token.db", client=client)
    assert client.cookies.get("kf_session") == "sess-cookie"


# ── Failure categories ───────────────────────────────────────────────────────────────────


async def test_bad_password_is_login_rejected_and_leaks_nothing(autologin_env: None, tmp_path: Path) -> None:
    stub = KiteStub(reject_login=True)
    async with _client(stub) as client:
        with pytest.raises(AutoLoginError) as excinfo:
            await perform_autologin(token_db=tmp_path / "kite_token.db", client=client)
    assert excinfo.value.category == CATEGORY_LOGIN_REJECTED
    assert excinfo.value.exit_code == 2
    message = str(excinfo.value)
    assert FAKE_PASSWORD not in message
    assert FAKE_TOTP_SECRET not in message
    assert "twofa" not in stub.seen_forms  # rejected login must stop the sequence


async def test_bad_totp_is_twofa_rejected_and_leaks_nothing(autologin_env: None, tmp_path: Path) -> None:
    stub = KiteStub(reject_twofa=True)
    async with _client(stub) as client:
        with pytest.raises(AutoLoginError) as excinfo:
            await perform_autologin(token_db=tmp_path / "kite_token.db", client=client)
    assert excinfo.value.category == CATEGORY_TWOFA_REJECTED
    assert excinfo.value.exit_code == 3
    message = str(excinfo.value)
    assert FAKE_PASSWORD not in message
    assert FAKE_TOTP_SECRET not in message
    assert stub.seen_forms["twofa"]["twofa_value"] not in message  # the generated code stays secret too


async def test_redirect_without_request_token_is_its_own_category(autologin_env: None, tmp_path: Path) -> None:
    stub = KiteStub(omit_request_token=True)
    async with _client(stub) as client:
        with pytest.raises(AutoLoginError) as excinfo:
            await perform_autologin(token_db=tmp_path / "kite_token.db", client=client)
    assert excinfo.value.category == CATEGORY_NO_REQUEST_TOKEN
    assert excinfo.value.exit_code == 4
    assert all("127.0.0.1" not in url for url in stub.requested_urls)


async def test_login_page_instead_of_redirect_is_no_request_token(autologin_env: None, tmp_path: Path) -> None:
    # Cookies not honoured -> /connect/login serves the login form (HTTP 200) instead of 302.
    stub = KiteStub(serve_login_page=True)
    async with _client(stub) as client:
        with pytest.raises(AutoLoginError) as excinfo:
            await perform_autologin(token_db=tmp_path / "kite_token.db", client=client)
    assert excinfo.value.category == CATEGORY_NO_REQUEST_TOKEN


async def test_exchange_failure_is_exchange_failed_and_leaks_no_secret(autologin_env: None, tmp_path: Path) -> None:
    stub = KiteStub(reject_exchange=True)
    async with _client(stub) as client:
        with pytest.raises(AutoLoginError) as excinfo:
            await perform_autologin(token_db=tmp_path / "kite_token.db", client=client)
    assert excinfo.value.category == CATEGORY_EXCHANGE_FAILED
    assert excinfo.value.exit_code == 5
    message = str(excinfo.value)
    assert FAKE_SECRET not in message
    assert FAKE_PASSWORD not in message
    assert FAKE_TOTP_SECRET not in message


async def test_redirect_chain_never_leaves_kite_without_a_token(autologin_env: None) -> None:
    # A hop to an unexpected third-party host must abort, not be followed.
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "kite.zerodha.com", "must not request a non-Kite host"
        return httpx.Response(302, headers={"location": "https://evil.example.com/steal"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AutoLoginError) as excinfo:
            await fetch_request_token(client)
    assert excinfo.value.category == CATEGORY_NO_REQUEST_TOKEN


# ── Idempotency and heartbeats ───────────────────────────────────────────────────────────


def _heartbeats(db: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(db) as conn:
        return list(conn.execute("SELECT event, detail FROM heartbeats ORDER BY ts"))


def test_fresh_token_short_circuits_without_touching_kite(
    autologin_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token_db = tmp_path / "kite_token.db"
    heartbeat_db = tmp_path / "capture.db"
    store_token("todays-token", db=token_db)  # created now -> fresh by definition

    async def must_not_run(**_: object) -> StoredToken:
        raise AssertionError("perform_autologin must not run when the stored token is fresh")

    monkeypatch.setattr(autologin, "perform_autologin", must_not_run)
    assert main(["--token-db", str(token_db), "--db", str(heartbeat_db)]) == 0
    events = _heartbeats(heartbeat_db)
    assert len(events) == 1
    assert events[0][0] == "autologin_skipped"
    assert "fresh" in events[0][1]
    assert "todays-token" not in capsys.readouterr().out  # confirmation only, never the token


def test_stale_token_triggers_a_real_login(
    autologin_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_db = tmp_path / "kite_token.db"
    heartbeat_db = tmp_path / "capture.db"
    store_token("stale-token", db=token_db, now=datetime(2026, 8, 20, 9, 0, tzinfo=IST))  # long past 06:00 flush

    stub = KiteStub()

    async def patched(*, token_db: Path | None = None, client: httpx.AsyncClient | None = None) -> StoredToken:
        async with _client(stub) as mock_client:
            return await perform_autologin(token_db=token_db, client=mock_client)

    monkeypatch.setattr(autologin, "perform_autologin", patched)
    assert main(["--token-db", str(token_db), "--db", str(heartbeat_db)]) == 0
    loaded = load_token(db=token_db)
    assert loaded is not None
    assert loaded.access_token == "fresh-access-token"
    assert [event for event, _ in _heartbeats(heartbeat_db)] == ["autologin_ok"]


def test_failed_main_exits_with_the_category_code_and_heartbeat(
    autologin_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    heartbeat_db = tmp_path / "capture.db"

    async def rejected(**_: object) -> StoredToken:
        raise AutoLoginError(CATEGORY_TWOFA_REJECTED, "HTTP 403, error_type=TwoFAException")

    monkeypatch.setattr(autologin, "perform_autologin", rejected)
    code = main(["--token-db", str(tmp_path / "kite_token.db"), "--db", str(heartbeat_db)])
    assert code == 3
    captured = capsys.readouterr()
    assert f"kite auto-login failed: {CATEGORY_TWOFA_REJECTED}" in captured.err
    assert FAKE_PASSWORD not in captured.err + captured.out
    events = _heartbeats(heartbeat_db)
    assert events[0][0] == "autologin_error"
    assert CATEGORY_TWOFA_REJECTED in events[0][1]


def test_success_output_and_heartbeat_never_contain_credentials_or_token(
    autologin_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token_db = tmp_path / "kite_token.db"
    heartbeat_db = tmp_path / "capture.db"
    stub = KiteStub()

    async def patched(*, token_db: Path | None = None, client: httpx.AsyncClient | None = None) -> StoredToken:
        async with _client(stub) as mock_client:
            return await perform_autologin(token_db=token_db, client=mock_client)

    monkeypatch.setattr(autologin, "perform_autologin", patched)
    assert main(["--token-db", str(token_db), "--db", str(heartbeat_db)]) == 0
    everything = capsys.readouterr().out + " ".join(detail for _, detail in _heartbeats(heartbeat_db))
    for secret in (FAKE_PASSWORD, FAKE_TOTP_SECRET, FAKE_SECRET, "fresh-access-token"):
        assert secret not in everything


# ── Capture-only constraint audit (extends test_options_capture's permanent sweep) ───────


def test_autologin_is_covered_by_the_order_write_audit() -> None:
    source = Path(autologin.__file__).read_text()
    for forbidden in FORBIDDEN_SOURCE_STRINGS:
        assert forbidden not in source, f"autologin.py references forbidden API string {forbidden!r}"
