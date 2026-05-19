import redis.asyncio as aioredis
from kiteconnect import KiteConnect

from app.config import get_settings

KITE_TOKEN_KEY = "kite:access_token"
KITE_TOKEN_TTL = 24 * 60 * 60  # 24 hours


def _get_kite_client() -> KiteConnect:
    settings = get_settings()
    return KiteConnect(api_key=settings.kite_api_key)


def get_login_url() -> str:
    kite = _get_kite_client()
    url: str = kite.login_url()
    return url


async def handle_callback(request_token: str, redis: aioredis.Redis) -> str:
    settings = get_settings()
    kite = KiteConnect(api_key=settings.kite_api_key)
    data = kite.generate_session(request_token, api_secret=settings.kite_api_secret)
    access_token: str = data["access_token"]
    await redis.set(KITE_TOKEN_KEY, access_token, ex=KITE_TOKEN_TTL)
    return access_token


async def get_stored_access_token(redis: aioredis.Redis) -> str | None:
    token = await redis.get(KITE_TOKEN_KEY)
    if isinstance(token, bytes):
        return token.decode()
    if isinstance(token, str):
        return token
    return None
