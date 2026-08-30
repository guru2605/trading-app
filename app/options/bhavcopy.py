"""Local archive of NSE's *official published* F&O bhavcopy.

Compliance
----------
docs/options-paper-trading-plan.md Sec 6 is the governing constraint. NSE's website Terms of
Use prohibit scraping/automated access **and**, separately, use of site data for "virtual
trading or simulation activities". Sec 6 concludes with the one carve-out this module relies
on, verbatim:

    Free NSE data remains fine for the uses that are neither automated-at-scale nor
    simulation: holiday calendars, expiry ladders, and the **official published bhavcopy**
    for EOD cross-checks.

So this module is deliberately narrow:

- It downloads only the daily settlement file that NSE publishes for public download. It does
  not touch ``/api/option-chain-indices`` or any other JSON endpoint, and it does not touch
  ``wss://streamer.nseindia.com``. Sec 6 says explicitly: do not design against that socket.
- One file per trading day, fetched at most once and then cached on disk. Re-running is a
  no-op. There is no polling loop.
- Range fetches sleep ``REQUEST_DELAY_SECONDS`` between requests, sized to stay under the
  ~3-4 requests/minute per IP that Sec 6 records NSE as tolerating.
- The archive exists for **EOD cross-checks** — reconciling a fill price or a settlement price
  against the exchange's own published number. Sec 6 rules out using free NSE data as the
  price feed that drives the simulation itself; that has to be licensed broker data (Sec 4.2).
  Nothing here is wired into a simulation loop, and it should not be.

Nothing in this module places, modifies or cancels an order.

Sources
-------
UDiFF (Unified Data Interface File Format) is the current daily-reports format, mandated by
SEBI's common data format initiative and live on NSE from 08-Jul-2024. Before that date NSE
published the legacy ``foDDMMMYYYYbhav.csv.zip``. Both URL shapes are encoded below; the
UDiFF cutover date is the switch.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

from app.options.calendar import is_trading_day
from app.options.contracts import Index

# ── Endpoints ────────────────────────────────────────────────────────────────────────────

#: First date on which NSE published the F&O bhavcopy in UDiFF format. Before this, the
#: legacy ``fo<DDMMMYYYY>bhav.csv.zip`` archive path applies.
UDIFF_START_DATE: date = date(2024, 7, 8)

#: UDiFF daily F&O bhavcopy (zipped CSV). ``{yyyymmdd}`` is the trade date.
UDIFF_URL_TEMPLATE: str = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{yyyymmdd}_F_0000.csv.zip"

#: Legacy daily F&O bhavcopy, used for trade dates before :data:`UDIFF_START_DATE`.
LEGACY_URL_TEMPLATE: str = (
    "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{yyyy}/{mon}/fo{ddmonyyyy}bhav.csv.zip"
)

#: Browser-shaped headers. NSE's archive host rejects requests without them. This mirrors the
#: header set already used by ``app.services.nse_data`` rather than inventing a second one.
NSE_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

#: NSE's archive host sets cookies on the homepage and 403s archive requests that lack them.
NSE_HOMEPAGE: str = "https://www.nseindia.com/"

#: Sec 6 records NSE rate-limiting to roughly 3-4 requests per minute per IP. 20 seconds keeps
#: a range backfill inside that, at the cost of being slow. Being slow is the correct trade.
REQUEST_DELAY_SECONDS: float = 20.0

#: Per-request timeout. The archive host is slow under load.
REQUEST_TIMEOUT_SECONDS: float = 30.0


# ── Local storage ────────────────────────────────────────────────────────────────────────

#: Root of the local archive. Overridable per call; the default is repo-relative so the data
#: never lands outside the project. Add ``data/`` to .gitignore — these files are large and
#: are NSE's, not ours, to redistribute (Sec 6: unlicensed redistribution, even free, is
#: treated as data vending).
DEFAULT_ARCHIVE_ROOT: Path = Path("data/bhavcopy/fo")


def archive_path(trade_date: date, root: Path | None = None) -> Path:
    """Local path for the extracted CSV of ``trade_date``'s F&O bhavcopy."""
    base = root if root is not None else DEFAULT_ARCHIVE_ROOT
    return base / f"{trade_date.year:04d}" / f"{trade_date.month:02d}" / f"fo_{trade_date:%Y%m%d}.csv"


def bhavcopy_url(trade_date: date) -> str:
    """Public NSE archive URL for ``trade_date``'s F&O bhavcopy."""
    if trade_date >= UDIFF_START_DATE:
        return UDIFF_URL_TEMPLATE.format(yyyymmdd=f"{trade_date:%Y%m%d}")
    return LEGACY_URL_TEMPLATE.format(
        yyyy=f"{trade_date:%Y}",
        mon=f"{trade_date:%b}".upper(),
        ddmonyyyy=f"{trade_date:%d%b%Y}".upper(),
    )


# ── Fetch ────────────────────────────────────────────────────────────────────────────────


class BhavcopyUnavailableError(RuntimeError):
    """NSE did not serve a bhavcopy for the requested date."""


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a single day's archive request."""

    trade_date: date
    path: Path
    downloaded: bool
    """False when the file was already present and the request was skipped."""


def _extract_csv(payload: bytes, trade_date: date) -> bytes:
    """Pull the single CSV member out of NSE's zipped bhavcopy."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not members:
            raise BhavcopyUnavailableError(f"No CSV inside the bhavcopy archive for {trade_date.isoformat()}")
        return archive.read(members[0])


async def fetch_bhavcopy(
    trade_date: date,
    *,
    root: Path | None = None,
    overwrite: bool = False,
    client: httpx.AsyncClient | None = None,
) -> FetchResult:
    """Download and store one trading day's official F&O bhavcopy.

    Returns immediately with ``downloaded=False`` if the file is already archived, unless
    ``overwrite`` is set. Pass ``client`` to reuse a primed session across a range fetch.
    """
    target = archive_path(trade_date, root)
    if target.exists() and not overwrite:
        return FetchResult(trade_date=trade_date, path=target, downloaded=False)

    if client is None:
        async with _new_client() as owned:
            await _prime(owned)
            payload = await _get(owned, trade_date)
    else:
        payload = await _get(client, trade_date)

    csv_bytes = _extract_csv(payload, trade_date)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(csv_bytes)
    return FetchResult(trade_date=trade_date, path=target, downloaded=True)


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=NSE_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)


async def _prime(client: httpx.AsyncClient) -> None:
    """Hit the homepage first so the archive request carries the cookies NSE expects."""
    # Priming is best-effort; the archive request below will surface any real failure.
    with contextlib.suppress(httpx.HTTPError):
        await client.get(NSE_HOMEPAGE)


async def _get(client: httpx.AsyncClient, trade_date: date) -> bytes:
    url = bhavcopy_url(trade_date)
    response = await client.get(url)
    if response.status_code == 404:
        raise BhavcopyUnavailableError(
            f"NSE has no F&O bhavcopy for {trade_date.isoformat()} ({url}) — "
            "the date is probably not a settlement day, or the file has not been published yet"
        )
    response.raise_for_status()
    return response.content


async def fetch_range(
    start: date,
    end: date,
    *,
    root: Path | None = None,
    overwrite: bool = False,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
) -> list[FetchResult]:
    """Archive every trading day in ``[start, end]``, politely.

    Skips weekends and NSE holidays (so no wasted request), skips days already archived, and
    sleeps ``delay_seconds`` between actual downloads to respect the rate limit recorded in
    Sec 6. Days NSE has no file for are reported and skipped rather than aborting the run.
    """
    results: list[FetchResult] = []
    async with _new_client() as client:
        await _prime(client)
        cursor = start
        first = True
        while cursor <= end:
            if not is_trading_day(cursor):
                cursor += timedelta(days=1)
                continue
            if archive_path(cursor, root).exists() and not overwrite:
                results.append(FetchResult(cursor, archive_path(cursor, root), downloaded=False))
                cursor += timedelta(days=1)
                continue
            if not first:
                await asyncio.sleep(delay_seconds)
            first = False
            # A day NSE has no file for is skipped, not fatal — see the docstring.
            with contextlib.suppress(BhavcopyUnavailableError):
                results.append(await fetch_bhavcopy(cursor, root=root, overwrite=overwrite, client=client))
            cursor += timedelta(days=1)
    return results


# ── Read ─────────────────────────────────────────────────────────────────────────────────

# UDiFF column names for the fields this project cares about. The legacy format used
# INSTRUMENT / SYMBOL / EXPIRY_DT / STRIKE_PR / OPTION_TYP / CLOSE / SETTLE_PR / OPEN_INT.
UDIFF_COLUMNS: dict[str, str] = {
    "instrument": "FinInstrmTp",
    "symbol": "TckrSymb",
    "expiry": "XpryDt",
    "strike": "StrkPric",
    "option_type": "OptnTp",
    "close": "ClsPric",
    "settlement": "SttlmPric",
    "open_interest": "OpnIntrst",
}

#: UDiFF ``FinInstrmTp`` value for an index option.
UDIFF_INDEX_OPTION: str = "IDO"

#: Legacy ``INSTRUMENT`` value for an index option.
LEGACY_INDEX_OPTION: str = "OPTIDX"


def load_bhavcopy(trade_date: date, root: Path | None = None) -> pd.DataFrame:
    """Read an archived bhavcopy from disk. Raises ``FileNotFoundError`` if not archived."""
    path = archive_path(trade_date, root)
    if not path.exists():
        raise FileNotFoundError(f"No archived bhavcopy for {trade_date.isoformat()} at {path}; fetch it first")
    frame = pd.read_csv(path)
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def index_options(frame: pd.DataFrame, index: Index) -> pd.DataFrame:
    """Rows of a bhavcopy that are options on ``index``, in either file format."""
    if UDIFF_COLUMNS["instrument"] in frame.columns:
        instrument_col = UDIFF_COLUMNS["instrument"]
        symbol_col = UDIFF_COLUMNS["symbol"]
        wanted = UDIFF_INDEX_OPTION
    elif "INSTRUMENT" in frame.columns:
        instrument_col = "INSTRUMENT"
        symbol_col = "SYMBOL"
        wanted = LEGACY_INDEX_OPTION
    else:
        raise ValueError(f"Unrecognised bhavcopy layout; columns were {list(frame.columns)[:10]}")

    mask = (frame[instrument_col].astype(str).str.strip() == wanted) & (
        frame[symbol_col].astype(str).str.strip() == index.value
    )
    return frame.loc[mask].copy()


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.options.bhavcopy",
        description="Archive NSE's official published F&O bhavcopy locally (EOD cross-checks only).",
    )
    parser.add_argument("start", type=date.fromisoformat, help="Start trade date, YYYY-MM-DD")
    parser.add_argument("end", type=date.fromisoformat, nargs="?", help="End trade date (defaults to start)")
    parser.add_argument("--root", type=Path, default=None, help=f"Archive root (default {DEFAULT_ARCHIVE_ROOT})")
    parser.add_argument("--overwrite", action="store_true", help="Re-download days already archived")
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY_SECONDS,
        help=f"Seconds between downloads (default {REQUEST_DELAY_SECONDS}; lower it at your own risk)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    end = args.end or args.start
    results = asyncio.run(
        fetch_range(args.start, end, root=args.root, overwrite=args.overwrite, delay_seconds=args.delay)
    )
    fetched = sum(1 for r in results if r.downloaded)
    print(f"{len(results)} trading day(s) archived, {fetched} newly downloaded")
    for result in results:
        marker = "+" if result.downloaded else "="
        print(f"  {marker} {result.trade_date.isoformat()}  {result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
