import asyncio
import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.deps import close_redis, get_redis
from app.routers import (
    alerts,
    analytics,
    audit,
    auth,
    backtest,
    behavior,
    journal,
    orders,
    portfolio,
    risk,
    rules,
    scanner,
    status,
    tax,
    trades,
    watchlist,
)
from app.routers.auth import kite_callback_router
from app.tasks.background_scanner import background_scanner_loop
from app.tasks.outcome_tracker import outcome_tracker_loop


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    redis = await get_redis()
    scanner_task = asyncio.create_task(background_scanner_loop(redis))
    outcome_task = asyncio.create_task(outcome_tracker_loop())
    yield
    scanner_task.cancel()
    outcome_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await scanner_task
    with contextlib.suppress(asyncio.CancelledError):
        await outcome_task
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="kite-trader", version="0.1.0", lifespan=lifespan)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(kite_callback_router)
    application.include_router(status.router)
    application.include_router(auth.router)
    application.include_router(audit.router)
    application.include_router(portfolio.router)
    application.include_router(trades.router)
    application.include_router(risk.router)
    application.include_router(alerts.router)
    application.include_router(watchlist.router)
    application.include_router(scanner.router)
    application.include_router(backtest.router)
    application.include_router(analytics.router)
    application.include_router(journal.router)
    application.include_router(behavior.router)
    application.include_router(orders.router)
    application.include_router(rules.router)
    application.include_router(tax.router)
    return application


app = create_app()
