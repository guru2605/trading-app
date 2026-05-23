from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.order import OrderPlaceRequest
from app.schemas.safety import SafetyConfig
from app.services.order import OrderService


def _order(**overrides: object) -> OrderPlaceRequest:
    defaults: dict[str, object] = {
        "tradingsymbol": "RELIANCE",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "quantity": 1,
        "price": 2500.0,
        "product": "CNC",
        "order_type": "LIMIT",
    }
    defaults.update(overrides)
    return OrderPlaceRequest(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_place_order_dry_run(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=True)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    service = OrderService(db_session, mock_redis)

    with patch.object(service.risk_engine.safety, "is_blocked", return_value=(False, "")):
        result = await service.place_order(_order())
        assert result.status == "SUCCESS"
        assert result.dry_run is True
        assert result.order_id == "DRY_RUN"


@pytest.mark.asyncio
async def test_place_order_blocked(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(panic_mode=True)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    service = OrderService(db_session, mock_redis)

    with patch.object(
        service.risk_engine.safety,
        "is_blocked",
        return_value=(True, "Panic mode is active. All orders blocked."),
    ):
        result = await service.place_order(_order())
        assert result.status == "BLOCKED"
        assert result.order_id is None


@pytest.mark.asyncio
async def test_place_order_real(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=False)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    mock_kite = AsyncMock()
    mock_kite.place_order = AsyncMock(return_value="123456")
    mock_kite.order_margins = AsyncMock(return_value=[{"total": 1000}])
    mock_kite.margins = AsyncMock(return_value={"equity": {"available": {"live_balance": 50000}}})
    service = OrderService(db_session, mock_redis, kite=mock_kite)

    with patch.object(service.risk_engine.safety, "is_blocked", return_value=(False, "")):
        result = await service.place_order(_order())
        assert result.status == "SUCCESS"
        assert result.dry_run is False
        assert result.order_id == "123456"
        mock_kite.place_order.assert_called_once()


@pytest.mark.asyncio
async def test_place_order_no_kite_real_mode(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=False)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    service = OrderService(db_session, mock_redis, kite=None)

    with patch.object(service.risk_engine.safety, "is_blocked", return_value=(False, "")):
        result = await service.place_order(_order())
        assert result.status == "ERROR"
        assert result.dry_run is False


@pytest.mark.asyncio
async def test_cancel_order(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    mock_kite = AsyncMock()
    mock_kite.cancel_order = AsyncMock(return_value="cancelled")
    service = OrderService(db_session, mock_redis, kite=mock_kite)

    result = await service.cancel_order("123456")
    assert result["status"] == "SUCCESS"
    mock_kite.cancel_order.assert_called_once_with("regular", "123456")


@pytest.mark.asyncio
async def test_cancel_order_no_kite(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    service = OrderService(db_session, mock_redis, kite=None)

    result = await service.cancel_order("123456")
    assert result["status"] == "ERROR"


@pytest.mark.asyncio
async def test_get_order_margins_with_kite(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    mock_kite = AsyncMock()
    mock_kite.order_margins = AsyncMock(return_value=[{"total": 2500}])
    mock_kite.margins = AsyncMock(return_value={"equity": {"available": {"live_balance": 50000}}})
    service = OrderService(db_session, mock_redis, kite=mock_kite)

    result = await service.get_order_margins(_order())
    assert result.total == 2500.0
    assert result.available == 50000.0
    assert result.sufficient is True


@pytest.mark.asyncio
async def test_get_order_margins_no_kite(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    service = OrderService(db_session, mock_redis, kite=None)

    result = await service.get_order_margins(_order())
    assert result.total == 0
    assert result.sufficient is False
