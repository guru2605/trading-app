from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.app_env == "development")

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
