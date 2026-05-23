"""Background scanner — pre-computes signals for all index stocks every hour."""

import asyncio
import logging
from datetime import UTC, datetime

import redis.asyncio as aioredis
from sqlalchemy import func, select

from app.data.indices import get_all_unique_symbols
from app.db.session import async_session
from app.models.signal import Signal
from app.services.scanner import ScannerService

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 3600  # 1 hour
POLL_INTERVAL_SECONDS = 60  # check for active signals every 60s


async def run_background_scan(redis: aioredis.Redis) -> None:
    """Run a single background scan of all index symbols and store metadata in Redis."""
    all_symbols = get_all_unique_symbols()
    logger.info("Background scan starting: %d unique symbols", len(all_symbols))
    start = datetime.now(UTC)

    try:
        async with async_session() as db:
            service = ScannerService(db)
            service._semaphore = asyncio.Semaphore(5)
            results, errors = await service.scan_symbols(all_symbols, timeframe="15minute")

        duration = (datetime.now(UTC) - start).total_seconds()
        now_iso = datetime.now(UTC).isoformat()

        await redis.set("scanner:last_scan", now_iso)
        await redis.hset(  # type: ignore[misc]
            "scanner:status",
            mapping={
                "last_scan": now_iso,
                "status": "completed",
                "symbols_scanned": str(len(all_symbols)),
                "signals_generated": str(len(results)),
                "errors_count": str(len(errors)),
                "duration_seconds": f"{duration:.1f}",
            },
        )

        logger.info(
            "Background scan complete: %d signals, %d errors in %.1fs",
            len(results),
            len(errors),
            duration,
        )
        if errors:
            logger.warning("Background scan errors: %s", errors[:10])

    except Exception:
        logger.exception("Background scan failed")
        now_iso = datetime.now(UTC).isoformat()
        await redis.hset(  # type: ignore[misc]
            "scanner:status",
            mapping={
                "last_scan": now_iso,
                "status": "error",
                "symbols_scanned": "0",
                "signals_generated": "0",
                "errors_count": "1",
                "duration_seconds": "0",
            },
        )


async def _has_active_signals() -> bool:
    """Check if any active signals exist in the database."""
    async with async_session() as db:
        result = await db.execute(select(func.count()).select_from(Signal).where(Signal.status == "active"))
        count = result.scalar_one()
        return count > 0


async def background_scanner_loop(redis: aioredis.Redis) -> None:
    """Run background scan in a loop. Rescans immediately if all signals are expired."""
    logger.info("Background scanner started (interval=%ds)", SCAN_INTERVAL_SECONDS)
    while True:
        await run_background_scan(redis)
        # Sleep in short intervals, re-scanning immediately if no active signals remain
        elapsed = 0
        while elapsed < SCAN_INTERVAL_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS
            if not await _has_active_signals():
                logger.info("No active signals remaining — triggering immediate rescan")
                break
