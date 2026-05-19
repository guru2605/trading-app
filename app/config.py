from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://kite:kite@localhost:5432/kite_trader"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Kite Connect
    kite_api_key: str = ""
    kite_api_secret: str = ""

    # App
    app_env: str = "development"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
