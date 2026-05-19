from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import async_session
from app.kite.auth import KITE_TOKEN_KEY
from app.kite.client import KiteClient

_redis_client: aioredis.Redis | None = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_kite_client(redis: aioredis.Redis = Depends(get_redis)) -> KiteClient:
    token = await redis.get(KITE_TOKEN_KEY)
    if not token:
        raise HTTPException(status_code=401, detail="Kite session not active. Please login first.")
    settings = get_settings()
    access_token = token.decode() if isinstance(token, bytes) else token
    return KiteClient(api_key=settings.kite_api_key, access_token=access_token)


async def get_optional_kite_client(redis: aioredis.Redis = Depends(get_redis)) -> KiteClient | None:
    token = await redis.get(KITE_TOKEN_KEY)
    if not token:
        return None
    settings = get_settings()
    access_token = token.decode() if isinstance(token, bytes) else token
    return KiteClient(api_key=settings.kite_api_key, access_token=access_token)
