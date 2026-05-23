from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.holding import Holding
from app.models.trade import Trade
from app.schemas.order import OrderPlaceRequest
from app.schemas.safety import SafetyConfig
from app.services.risk_engine import RiskEngineService


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


# --- Safety Check ---


@pytest.mark.asyncio
async def test_safety_check_passes_when_not_blocked(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        safety = next(r for r in results if r.stage == "safety_check")
        assert safety.passed is True


@pytest.mark.asyncio
async def test_safety_check_blocks_panic_mode(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(panic_mode=True)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(True, "Panic mode is active. All orders blocked.")):
        results = await engine.validate_order(_order())
        safety = next(r for r in results if r.stage == "safety_check")
        assert safety.passed is False
        assert "Panic" in safety.reason


@pytest.mark.asyncio
async def test_safety_check_blocks_cooldown(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(
        engine.safety, "is_blocked", return_value=(True, "Loss cooldown is active. Orders temporarily blocked.")
    ):
        results = await engine.validate_order(_order())
        safety = next(r for r in results if r.stage == "safety_check")
        assert safety.passed is False
        assert "cooldown" in safety.reason


# --- Margin Check ---


@pytest.mark.asyncio
async def test_margin_check_passes_in_dry_run(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=True)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        margin = next(r for r in results if r.stage == "margin_check")
        assert margin.passed is True
        assert "dry_run" in margin.reason


@pytest.mark.asyncio
async def test_margin_check_passes_with_sufficient_margin(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=False)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    mock_kite = AsyncMock()
    mock_kite.order_margins = AsyncMock(return_value=[{"total": 1000}])
    mock_kite.margins = AsyncMock(return_value={"equity": {"available": {"live_balance": 5000}}})
    engine = RiskEngineService(db_session, mock_redis, kite=mock_kite)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        margin = next(r for r in results if r.stage == "margin_check")
        assert margin.passed is True


@pytest.mark.asyncio
async def test_margin_check_blocks_insufficient_margin(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=False)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    mock_kite = AsyncMock()
    mock_kite.order_margins = AsyncMock(return_value=[{"total": 5000}])
    mock_kite.margins = AsyncMock(return_value={"equity": {"available": {"live_balance": 1000}}})
    engine = RiskEngineService(db_session, mock_redis, kite=mock_kite)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        margin = next(r for r in results if r.stage == "margin_check")
        assert margin.passed is False
        assert "Insufficient" in margin.reason


# --- Exposure Check ---


@pytest.mark.asyncio
async def test_exposure_check_passes_within_limits(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(max_order_value=50000)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order(quantity=1, price=2500.0))
        exposure = next(r for r in results if r.stage == "exposure_check")
        assert exposure.passed is True


@pytest.mark.asyncio
async def test_exposure_check_blocks_exceeding_max_value(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(max_order_value=1000)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order(quantity=10, price=2500.0))
        exposure = next(r for r in results if r.stage == "exposure_check")
        assert exposure.passed is False
        assert "exceeds max" in exposure.reason


@pytest.mark.asyncio
async def test_exposure_check_blocks_high_concentration(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(max_order_value=1000000, max_position_pct=10)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())

    # Add a small existing holding so new order dominates
    holding = Holding(
        tradingsymbol="TCS",
        exchange="NSE",
        quantity=1,
        average_price=100,
        last_price=100,
        pnl=0,
        day_change=0,
        day_change_pct=0,
    )
    db_session.add(holding)
    await db_session.commit()

    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        # Order value = 100 * 2500 = 250000, portfolio = 100, concentration very high
        results = await engine.validate_order(_order(quantity=100, price=2500.0))
        exposure = next(r for r in results if r.stage == "exposure_check")
        assert exposure.passed is False
        assert "concentration" in exposure.reason


# --- Drawdown Check ---


@pytest.mark.asyncio
async def test_drawdown_check_passes_no_loss(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(max_daily_loss=10000)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        drawdown = next(r for r in results if r.stage == "drawdown_check")
        assert drawdown.passed is True


@pytest.mark.asyncio
async def test_drawdown_check_blocks_excessive_loss(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(max_daily_loss=5000)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())

    now = datetime.now(UTC)
    # Buy high, sell low = loss
    db_session.add(
        Trade(
            order_id="buy1",
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=100,
            price=2500.0,
            product="CNC",
            order_type="MARKET",
            status="COMPLETE",
            created_at=now,
        )
    )
    db_session.add(
        Trade(
            order_id="sell1",
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="SELL",
            quantity=100,
            price=2400.0,
            product="CNC",
            order_type="MARKET",
            status="COMPLETE",
            created_at=now,
        )
    )
    await db_session.commit()

    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        drawdown = next(r for r in results if r.stage == "drawdown_check")
        # sell_value=240000, buy_value=250000 → pnl=-10000, exceeds 5000
        assert drawdown.passed is False
        assert "Daily loss" in drawdown.reason


# --- Rate Limit Check ---


@pytest.mark.asyncio
async def test_rate_limit_check_passes_below_limit(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(max_orders_per_day=10)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        rate = next(r for r in results if r.stage == "rate_limit_check")
        assert rate.passed is True


@pytest.mark.asyncio
async def test_rate_limit_check_blocks_at_limit(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(max_orders_per_day=2)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())

    now = datetime.now(UTC)
    for i in range(2):
        db_session.add(
            AuditEvent(
                event_type="order.placed",
                entity_type="order",
                entity_id=f"ord_{i}",
                payload={"tradingsymbol": "TCS"},
                source="system",
                created_at=now,
            )
        )
    await db_session.commit()

    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        rate = next(r for r in results if r.stage == "rate_limit_check")
        assert rate.passed is False
        assert "Rate limit" in rate.reason


# --- Duplicate Check ---


@pytest.mark.asyncio
async def test_duplicate_check_passes_no_recent(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig()
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        dup = next(r for r in results if r.stage == "duplicate_check")
        assert dup.passed is True


@pytest.mark.asyncio
async def test_duplicate_check_blocks_recent_same_order(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig()
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())

    now = datetime.now(UTC)
    db_session.add(
        AuditEvent(
            event_type="order.placed",
            entity_type="order",
            entity_id="ord_1",
            payload={"tradingsymbol": "RELIANCE", "transaction_type": "BUY"},
            source="system",
            created_at=now,
        )
    )
    await db_session.commit()

    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        dup = next(r for r in results if r.stage == "duplicate_check")
        assert dup.passed is False
        assert "Duplicate" in dup.reason


@pytest.mark.asyncio
async def test_duplicate_check_passes_different_symbol(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig()
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())

    now = datetime.now(UTC)
    db_session.add(
        AuditEvent(
            event_type="order.placed",
            entity_type="order",
            entity_id="ord_1",
            payload={"tradingsymbol": "TCS", "transaction_type": "BUY"},
            source="system",
            created_at=now,
        )
    )
    await db_session.commit()

    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        dup = next(r for r in results if r.stage == "duplicate_check")
        assert dup.passed is True


# --- Full Pipeline ---


@pytest.mark.asyncio
async def test_full_pipeline_all_pass(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=True)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order())
        assert len(results) == 6
        assert all(r.passed for r in results)


@pytest.mark.asyncio
async def test_market_order_skips_exposure(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=True)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())
    engine = RiskEngineService(db_session, mock_redis)

    with patch.object(engine.safety, "is_blocked", return_value=(False, "")):
        results = await engine.validate_order(_order(order_type="MARKET", price=None))
        exposure = next(r for r in results if r.stage == "exposure_check")
        assert exposure.passed is True
        assert "skipped" in exposure.reason
