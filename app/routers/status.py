from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/_status")
async def health_check() -> dict[str, Any]:
    return {"service": "kite-trader", "status": "ok"}
