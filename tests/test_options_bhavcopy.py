"""Tests for app.options.bhavcopy — local archive of NSE's official published F&O bhavcopy.

No test here touches the network. Sec 6 of the plan doc rules out automated access at scale;
a test suite that hammered nsearchives on every CI run would be exactly that.
"""

import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.options.bhavcopy import (
    DEFAULT_ARCHIVE_ROOT,
    LEGACY_INDEX_OPTION,
    NSE_HEADERS,
    NSE_HOMEPAGE,
    REQUEST_DELAY_SECONDS,
    UDIFF_COLUMNS,
    UDIFF_INDEX_OPTION,
    UDIFF_START_DATE,
    BhavcopyUnavailableError,
    FetchResult,
    _extract_csv,
    archive_path,
    bhavcopy_url,
    fetch_bhavcopy,
    index_options,
    load_bhavcopy,
)
from app.options.contracts import Index

# ── URL selection ────────────────────────────────────────────────────────────────────────


def test_udiff_url_from_the_cutover_date() -> None:
    url = bhavcopy_url(UDIFF_START_DATE)
    assert url == ("https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_20240708_F_0000.csv.zip")


def test_legacy_url_before_the_cutover_date() -> None:
    url = bhavcopy_url(date(2024, 7, 5))
    assert url == ("https://nsearchives.nseindia.com/content/historical/DERIVATIVES/2024/JUL/fo05JUL2024bhav.csv.zip")


@pytest.mark.parametrize(
    ("on", "expect_udiff"),
    [
        (date(2024, 7, 4), False),
        (date(2024, 7, 8), True),
        (date(2026, 8, 28), True),
    ],
)
def test_url_format_switches_at_the_cutover(on: date, expect_udiff: bool) -> None:
    assert ("/content/fo/BhavCopy_NSE_FO" in bhavcopy_url(on)) is expect_udiff


def test_urls_are_https_and_point_at_the_archive_host() -> None:
    for on in (date(2024, 1, 3), date(2026, 8, 28)):
        assert bhavcopy_url(on).startswith("https://nsearchives.nseindia.com/")


def test_only_the_published_archive_is_reachable() -> None:
    # Sec 6: the option-chain JSON API and wss://streamer.nseindia.com are off limits, and only
    # the officially published bhavcopy is carved out. Every endpoint this module can construct
    # must therefore be an nsearchives archive path (or the homepage, hit only for cookies).
    endpoints = [bhavcopy_url(date(2024, 1, 3)), bhavcopy_url(date(2026, 8, 28)), NSE_HOMEPAGE]
    for endpoint in endpoints:
        assert endpoint.startswith("https://")
        assert "/api/" not in endpoint
        assert not endpoint.startswith("ws")
        assert endpoint in (NSE_HOMEPAGE,) or endpoint.startswith("https://nsearchives.nseindia.com/")


# ── Local paths ──────────────────────────────────────────────────────────────────────────


def test_archive_path_is_year_month_partitioned(tmp_path: Path) -> None:
    path = archive_path(date(2026, 3, 9), tmp_path)
    assert path == tmp_path / "2026" / "03" / "fo_20260309.csv"


def test_archive_path_defaults_under_the_repo_data_dir() -> None:
    path = archive_path(date(2026, 3, 9))
    assert DEFAULT_ARCHIVE_ROOT in path.parents
    assert not path.is_absolute()  # gitignored `data/`, never outside the project


def test_rate_limit_delay_stays_under_four_requests_a_minute() -> None:
    # Sec 6 records NSE tolerating roughly 3-4 requests/minute per IP.
    assert 60 / REQUEST_DELAY_SECONDS <= 4


def test_requests_are_browser_shaped() -> None:
    assert "User-Agent" in NSE_HEADERS
    assert NSE_HEADERS["Referer"] == "https://www.nseindia.com/"


# ── Zip extraction ───────────────────────────────────────────────────────────────────────


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_extract_csv_pulls_the_single_member() -> None:
    payload = _zip_bytes({"BhavCopy_NSE_FO_0_0_0_20260828_F_0000.csv": b"TckrSymb\nNIFTY\n"})
    assert _extract_csv(payload, date(2026, 8, 28)) == b"TckrSymb\nNIFTY\n"


def test_extract_csv_ignores_non_csv_members() -> None:
    payload = _zip_bytes({"readme.txt": b"junk", "fo28082026bhav.csv": b"SYMBOL\nNIFTY\n"})
    assert _extract_csv(payload, date(2026, 8, 28)) == b"SYMBOL\nNIFTY\n"


def test_extract_csv_raises_when_the_archive_has_no_csv() -> None:
    payload = _zip_bytes({"readme.txt": b"junk"})
    with pytest.raises(BhavcopyUnavailableError, match="No CSV inside"):
        _extract_csv(payload, date(2026, 8, 28))


# ── Cache behaviour ──────────────────────────────────────────────────────────────────────


async def test_fetch_skips_the_network_when_already_archived(tmp_path: Path) -> None:
    on = date(2026, 8, 28)
    target = archive_path(on, tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"TckrSymb\nNIFTY\n")

    # client=None would build a real AsyncClient; reaching that line is the failure mode this
    # test exists to catch, so passing None here is deliberate.
    result = await fetch_bhavcopy(on, root=tmp_path)

    assert result == FetchResult(trade_date=on, path=target, downloaded=False)


# ── Reading ──────────────────────────────────────────────────────────────────────────────

UDIFF_CSV = (
    "FinInstrmTp,TckrSymb,XpryDt,StrkPric,OptnTp,ClsPric,SttlmPric,OpnIntrst\n"
    "IDO,NIFTY,2026-09-01,24800,CE,146.05,146.05,1250\n"
    "IDO,NIFTY,2026-09-01,24800,PE,131.20,131.20,980\n"
    "IDO,BANKNIFTY,2026-09-29,54100,CE,412.35,412.35,640\n"
    "STF,NIFTY,2026-09-29,0,,24812.35,24812.35,55000\n"
    "IDO,FINNIFTY,2026-09-01,26000,CE,88.10,88.10,120\n"
)

LEGACY_CSV = (
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,CLOSE,SETTLE_PR,OPEN_INT\n"
    "OPTIDX,NIFTY,25-JAN-2024,21500,CE,120.50,120.50,900\n"
    "OPTIDX,BANKNIFTY,25-JAN-2024,46000,PE,310.75,310.75,410\n"
    "FUTIDX,NIFTY,25-JAN-2024,0,XX,21520.00,21520.00,40000\n"
)


def _archive(csv_text: str, on: date, root: Path) -> None:
    target = archive_path(on, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(csv_text)


def test_load_bhavcopy_raises_when_not_archived(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No archived bhavcopy"):
        load_bhavcopy(date(2026, 8, 28), tmp_path)


def test_load_bhavcopy_strips_column_whitespace(tmp_path: Path) -> None:
    on = date(2026, 8, 28)
    _archive("  FinInstrmTp , TckrSymb \nIDO,NIFTY\n", on, tmp_path)
    frame = load_bhavcopy(on, tmp_path)
    assert list(frame.columns) == ["FinInstrmTp", "TckrSymb"]


def test_index_options_filters_udiff_layout(tmp_path: Path) -> None:
    on = date(2026, 8, 28)
    _archive(UDIFF_CSV, on, tmp_path)
    frame = load_bhavcopy(on, tmp_path)

    nifty = index_options(frame, Index.NIFTY)
    assert len(nifty) == 2  # the two IDO rows; the STF future is excluded
    assert set(nifty[UDIFF_COLUMNS["option_type"]]) == {"CE", "PE"}
    assert set(nifty[UDIFF_COLUMNS["instrument"]]) == {UDIFF_INDEX_OPTION}

    banknifty = index_options(frame, Index.BANKNIFTY)
    assert len(banknifty) == 1
    # FINNIFTY is present in the file but is not an Index we support, so it never appears.
    assert "FINNIFTY" not in set(nifty[UDIFF_COLUMNS["symbol"]]) | set(banknifty[UDIFF_COLUMNS["symbol"]])


def test_index_options_filters_legacy_layout(tmp_path: Path) -> None:
    on = date(2024, 1, 18)
    _archive(LEGACY_CSV, on, tmp_path)
    frame = load_bhavcopy(on, tmp_path)

    nifty = index_options(frame, Index.NIFTY)
    assert len(nifty) == 1  # OPTIDX only; FUTIDX excluded
    assert set(nifty["INSTRUMENT"]) == {LEGACY_INDEX_OPTION}
    assert len(index_options(frame, Index.BANKNIFTY)) == 1


def test_index_options_rejects_an_unrecognised_layout() -> None:
    frame = pd.DataFrame({"foo": [1], "bar": [2]})
    with pytest.raises(ValueError, match="Unrecognised bhavcopy layout"):
        index_options(frame, Index.NIFTY)


def test_index_options_returns_a_copy(tmp_path: Path) -> None:
    on = date(2026, 8, 28)
    _archive(UDIFF_CSV, on, tmp_path)
    frame = load_bhavcopy(on, tmp_path)

    subset = index_options(frame, Index.NIFTY)
    subset.loc[subset.index[0], UDIFF_COLUMNS["close"]] = 999.0
    assert frame.loc[0, UDIFF_COLUMNS["close"]] != 999.0
