from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_db, get_redis
from app.kite.auth import get_login_url, get_stored_access_token, handle_callback
from app.services.audit import AuditService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login() -> RedirectResponse:
    url = get_login_url()
    return RedirectResponse(url=url)


@router.get("/callback")
async def callback(
    request_token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, Any]:
    try:
        access_token = await handle_callback(request_token, redis)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {e}") from e

    audit = AuditService(db)
    await audit.log(
        event_type="auth.login",
        entity_type="session",
        payload={"token_prefix": access_token[:8] + "..."},
        source="kite",
    )
    return {"authenticated": True}


# Kite redirects to the root URL with ?request_token=...&status=success
# This catches that redirect, processes the token, and sends user to the frontend.
kite_callback_router = APIRouter()


@kite_callback_router.get("/", response_model=None)
async def root_kite_callback(
    request: Request,
    request_token: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> RedirectResponse | dict[str, Any]:
    if request_token and status == "success":
        try:
            access_token = await handle_callback(request_token, redis)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Authentication failed: {e}") from e

        audit = AuditService(db)
        await audit.log(
            event_type="auth.login",
            entity_type="session",
            payload={"token_prefix": access_token[:8] + "..."},
            source="kite",
        )
        # Redirect to the frontend origin that initiated the login
        settings = get_settings()
        frontend_url = settings.cors_origins.split(",")[0].strip()
        referer = request.headers.get("referer", "")
        for origin in settings.cors_origins.split(","):
            origin = origin.strip()
            if referer.startswith(origin):
                frontend_url = origin
                break
        return RedirectResponse(url=frontend_url)
    return {"service": "kite-trader", "hint": "Use /api/auth/login to authenticate"}


@router.get("/status")
async def auth_status(
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, Any]:
    token = await get_stored_access_token(redis)
    return {"authenticated": token is not None}
