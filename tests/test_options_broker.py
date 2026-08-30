"""Tests for app.options.broker — Kite Connect auth for the capture pipeline.

Pure-logic tests only. Nothing here touches the network: the one HTTP interaction
(``exchange_request_token``) is exercised through ``httpx.MockTransport``.
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import app.options.broker as broker
from app.options.broker import (
    ENV_API_KEY,
    ENV_API_SECRET,
    KITE_LOGIN_URL_TEMPLATE,
    TOKEN_EXPIRY_HOUR,
    StoredToken,
    api_key,
    compute_checksum,
    create_auth_app,
    exchange_request_token,
    is_fresh,
    load_token,
    login_url,
    require_fresh_token,
    store_token,
    token_expiry,
)
from app.options.calendar import IST

FAKE_KEY = "testkey123"
FAKE_SECRET = "testsecret456"


@pytest.fixture
def kite_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(ENV_API_SECRET, FAKE_SECRET)


# ── Environment and login URL ────────────────────────────────────────────────────────────


def test_missing_api_key_fails_loudly_without_leaking_anything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    monkeypatch.setenv(ENV_API_SECRET, FAKE_SECRET)
    with pytest.raises(RuntimeError, match=ENV_API_KEY) as excinfo:
        api_key()
    assert FAKE_SECRET not in str(excinfo.value)


def test_login_url_embeds_api_key_and_v3(kite_env: None) -> None:
    url = login_url()
    assert url == KITE_LOGIN_URL_TEMPLATE.format(api_key=FAKE_KEY)
    assert url.startswith("https://kite.zerodha.com/connect/login")
    assert "v=3" in url
    assert FAKE_SECRET not in url  # only the public identifier may appear


# ── Checksum ─────────────────────────────────────────────────────────────────────────────


def test_checksum_is_sha256_of_key_token_secret() -> None:
    # Independent reconstruction of the Kite Connect v3 recipe.
    expected = hashlib.sha256(b"k1rt2s3").hexdigest()
    assert compute_checksum("k1", "rt2", "s3") == expected
    assert len(compute_checksum("a", "b", "c")) == 64


# ── Token expiry (dies at the 06:00 IST daily flush) ─────────────────────────────────────


def test_token_created_after_six_lives_until_six_next_day() -> None:
    created = datetime(2026, 8, 28, 7, 30, tzinfo=IST)
    assert token_expiry(created) == datetime(2026, 8, 29, TOKEN_EXPIRY_HOUR, 0, tzinfo=IST)


def test_token_created_before_six_dies_the_same_morning() -> None:
    created = datetime(2026, 8, 28, 1, 0, tzinfo=IST)
    assert token_expiry(created) == datetime(2026, 8, 28, TOKEN_EXPIRY_HOUR, 0, tzinfo=IST)


def test_token_created_exactly_at_six_lives_until_six_next_day() -> None:
    created = datetime(2026, 8, 28, TOKEN_EXPIRY_HOUR, 0, tzinfo=IST)
    assert token_expiry(created) == datetime(2026, 8, 29, TOKEN_EXPIRY_HOUR, 0, tzinfo=IST)


def test_token_expiry_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="[Nn]aive"):
        token_expiry(datetime(2026, 8, 28, 7, 30))


def test_token_expiry_normalises_other_timezones_to_ist() -> None:
    # 03:00 UTC on the 28th is 08:30 IST on the 28th -> expires 06:00 IST on the 29th.
    created = datetime(2026, 8, 28, 3, 0, tzinfo=UTC)
    assert token_expiry(created) == datetime(2026, 8, 29, TOKEN_EXPIRY_HOUR, 0, tzinfo=IST)


def test_is_fresh_boundaries() -> None:
    created = datetime(2026, 8, 28, 9, 0, tzinfo=IST)
    just_before = datetime(2026, 8, 29, 5, 59, 59, tzinfo=IST)
    at_flush = datetime(2026, 8, 29, 6, 0, tzinfo=IST)
    assert is_fresh(created, just_before) is True
    assert is_fresh(created, at_flush) is False


def test_stored_token_freshness_helpers() -> None:
    token = StoredToken(access_token="tok", created_at=datetime(2026, 8, 28, 9, 0, tzinfo=IST))
    assert token.expires_at == datetime(2026, 8, 29, 6, 0, tzinfo=IST)
    assert token.fresh(datetime(2026, 8, 28, 15, 0, tzinfo=IST)) is True
    assert token.fresh(datetime(2026, 8, 29, 9, 0, tzinfo=IST)) is False


# ── SQLite token store ───────────────────────────────────────────────────────────────────


def test_store_and_load_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "kite_token.db"
    created = datetime(2026, 8, 28, 8, 45, tzinfo=IST)
    stored = store_token("day-token", db=db, now=created)
    loaded = load_token(db=db)
    assert loaded is not None
    assert loaded.access_token == "day-token"
    assert loaded.created_at == created
    assert loaded.expires_at == stored.expires_at


def test_store_is_a_single_row_upsert(tmp_path: Path) -> None:
    db = tmp_path / "kite_token.db"
    store_token("first", db=db, now=datetime(2026, 8, 27, 8, 0, tzinfo=IST))
    store_token("second", db=db, now=datetime(2026, 8, 28, 8, 0, tzinfo=IST))
    loaded = load_token(db=db)
    assert loaded is not None
    assert loaded.access_token == "second"


def test_load_from_a_missing_db_is_none(tmp_path: Path) -> None:
    assert load_token(db=tmp_path / "never-created.db") is None


def test_require_fresh_token_when_missing(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="No Kite access token"):
        require_fresh_token(db=tmp_path / "never-created.db")


def test_require_fresh_token_when_stale_names_the_expiry_but_not_the_token(tmp_path: Path) -> None:
    db = tmp_path / "kite_token.db"
    store_token("yesterdays-token", db=db, now=datetime(2026, 8, 27, 9, 0, tzinfo=IST))
    with pytest.raises(RuntimeError, match="STALE") as excinfo:
        require_fresh_token(db=db, now=datetime(2026, 8, 28, 9, 0, tzinfo=IST))
    assert "yesterdays-token" not in str(excinfo.value)


def test_require_fresh_token_when_fresh(tmp_path: Path) -> None:
    db = tmp_path / "kite_token.db"
    store_token("todays-token", db=db, now=datetime(2026, 8, 28, 8, 0, tzinfo=IST))
    token = require_fresh_token(db=db, now=datetime(2026, 8, 28, 9, 30, tzinfo=IST))
    assert token.access_token == "todays-token"


# ── Token exchange (MockTransport — no network) ──────────────────────────────────────────


async def test_exchange_posts_the_documented_checksum(kite_env: None) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(httpx.QueryParams(request.content.decode())))
        assert request.headers["X-Kite-Version"] == "3"
        return httpx.Response(
            200,
            json={"status": "success", "data": {"access_token": "fresh-token"}},
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        token = await exchange_request_token("reqtok", client=client)
    assert token == "fresh-token"
    assert seen["api_key"] == FAKE_KEY
    assert seen["checksum"] == compute_checksum(FAKE_KEY, "reqtok", FAKE_SECRET)


async def test_exchange_failure_is_loud_but_leaks_no_secret(kite_env: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"status": "error", "error_type": "TokenException", "message": "Token is invalid"},
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="TokenException") as excinfo:
            await exchange_request_token("reqtok", client=client)
    assert FAKE_SECRET not in str(excinfo.value)


# ── Auth app routes ──────────────────────────────────────────────────────────────────────


def test_login_route_redirects_to_zerodha(kite_env: None) -> None:
    client = TestClient(create_auth_app())
    response = client.get("/kite/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("https://kite.zerodha.com/connect/login")


def test_callback_rejects_a_failed_login(kite_env: None) -> None:
    client = TestClient(create_auth_app())
    assert client.get("/kite/callback", params={"status": "error"}).status_code == 400
    assert client.get("/kite/callback", params={"status": "success"}).status_code == 400  # no request_token


def test_callback_stores_the_token_but_never_echoes_it(
    kite_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "kite_token.db"
    monkeypatch.setattr(broker, "DEFAULT_TOKEN_DB", db)

    async def fake_exchange(request_token: str, **_: object) -> str:
        assert request_token == "reqtok"
        return "fresh-token"

    monkeypatch.setattr(broker, "exchange_request_token", fake_exchange)
    client = TestClient(create_auth_app())
    response = client.get("/kite/callback", params={"request_token": "reqtok", "status": "success"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["stored"] is True
    assert "fresh-token" not in response.text  # confirmation only, never the token
    loaded = load_token(db=db)
    assert loaded is not None
    assert loaded.access_token == "fresh-token"
