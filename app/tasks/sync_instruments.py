import asyncio
import logging

from kiteconnect import KiteConnect
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.kite.auth import KITE_TOKEN_KEY
from app.models.instrument import Instrument

logger = logging.getLogger(__name__)


async def sync_instruments(db: AsyncSession, access_token: str | None = None) -> int:
    settings = get_settings()
    kite = KiteConnect(api_key=settings.kite_api_key)

    if access_token:
        kite.set_access_token(access_token)
    else:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
        try:
            token = await r.get(KITE_TOKEN_KEY)
            if not token:
                raise RuntimeError("No access token available. Please login first.")
            kite.set_access_token(token)
        finally:
            await r.aclose()

    instruments = await asyncio.to_thread(kite.instruments)
    logger.info("Fetched %d instruments from Kite", len(instruments))

    # Delete-and-replace strategy
    await db.execute(delete(Instrument))

    rows = []
    for inst in instruments:
        try:
            rows.append(
                Instrument(
                    instrument_token=int(inst["instrument_token"]),
                    exchange_token=int(inst["exchange_token"]),
                    tradingsymbol=str(inst["tradingsymbol"]),
                    name=str(inst.get("name", "")),
                    exchange=str(inst["exchange"]),
                    segment=str(inst.get("segment", "")),
                    instrument_type=str(inst.get("instrument_type", "")),
                    lot_size=int(inst.get("lot_size", 1)),
                    tick_size=float(inst.get("tick_size", 0.05)),
                    expiry=str(inst["expiry"]) if inst.get("expiry") else None,
                    strike=float(inst["strike"]) if inst.get("strike") else None,
                    last_price=float(inst["last_price"]) if inst.get("last_price") else None,
                )
            )
        except (ValueError, TypeError):
            logger.warning("Skipping invalid instrument: %s", inst.get("tradingsymbol", "unknown"))
            continue

    db.add_all(rows)
    await db.commit()
    logger.info("Synced %d instruments to database", len(rows))
    return len(rows)
