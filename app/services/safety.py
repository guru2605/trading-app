from datetime import UTC, datetime

import redis.asyncio as aioredis

from app.schemas.safety import SafetyConfig

SAFETY_CONFIG_KEY = "kite:safety:config"
COOLDOWN_KEY = "kite:safety:cooldown_until"


class SafetyService:
    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis

    async def get_config(self) -> SafetyConfig:
        data = await self.redis.get(SAFETY_CONFIG_KEY)
        if data is None:
            return SafetyConfig()
        raw = data if isinstance(data, str) else data.decode()
        return SafetyConfig.model_validate_json(raw)

    async def update_config(self, updates: dict[str, object]) -> SafetyConfig:
        config = await self.get_config()
        updated = config.model_copy(update=updates)
        await self.redis.set(SAFETY_CONFIG_KEY, updated.model_dump_json())
        return updated

    async def activate_panic(self) -> SafetyConfig:
        return await self.update_config({"panic_mode": True})

    async def deactivate_panic(self) -> SafetyConfig:
        return await self.update_config({"panic_mode": False})

    async def set_cooldown(self, until_iso: str) -> None:
        await self.redis.set(COOLDOWN_KEY, until_iso)

    async def clear_cooldown(self) -> None:
        await self.redis.delete(COOLDOWN_KEY)

    async def is_cooldown_active(self) -> bool:
        value = await self.redis.get(COOLDOWN_KEY)
        if value is None:
            return False
        raw = value if isinstance(value, str) else value.decode()
        try:
            cooldown_until = datetime.fromisoformat(raw)
            return datetime.now(UTC) < cooldown_until
        except ValueError:
            return False

    @staticmethod
    def is_trading_hours() -> bool:
        now = datetime.now(UTC)
        # IST = UTC + 5:30. Market hours: 9:15 - 15:30 IST
        ist_hour = now.hour + 5
        ist_minute = now.minute + 30
        if ist_minute >= 60:
            ist_hour += 1
            ist_minute -= 60
        if ist_hour >= 24:
            ist_hour -= 24

        market_open = ist_hour * 60 + ist_minute  # minutes since midnight IST
        open_time = 9 * 60 + 15  # 9:15
        close_time = 15 * 60 + 30  # 15:30
        return open_time <= market_open <= close_time

    async def is_blocked(self) -> tuple[bool, str]:
        config = await self.get_config()
        if config.panic_mode:
            return True, "Panic mode is active. All orders blocked."
        if not self.is_trading_hours():
            return True, "Outside trading hours (9:15-15:30 IST)."
        if await self.is_cooldown_active():
            return True, "Loss cooldown is active. Orders temporarily blocked."
        return False, ""
