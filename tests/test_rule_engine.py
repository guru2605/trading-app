import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade
from app.schemas.safety import SafetyConfig
from app.services.rule_engine import RuleEngineService

# --- CRUD ---


@pytest.mark.asyncio
async def test_create_rule(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    service = RuleEngineService(db_session, mock_redis)
    rule = await service.create_rule(
        name="Buy RELIANCE dip",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=10,
        condition=json.dumps({"type": "price_below", "value": 2000}),
    )
    assert rule.id is not None
    assert rule.name == "Buy RELIANCE dip"
    assert rule.is_active is True


@pytest.mark.asyncio
async def test_list_rules(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    service = RuleEngineService(db_session, mock_redis)
    await service.create_rule(
        name="Rule 1",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        condition="",
    )
    await service.create_rule(
        name="Rule 2",
        tradingsymbol="TCS",
        exchange="NSE",
        transaction_type="SELL",
        quantity=1,
        condition="",
    )
    rules = await service.list_rules()
    assert len(rules) == 2


@pytest.mark.asyncio
async def test_list_rules_filter_active(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    service = RuleEngineService(db_session, mock_redis)
    await service.create_rule(
        name="Active",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        condition="",
    )
    rule2 = await service.create_rule(
        name="Inactive",
        tradingsymbol="TCS",
        exchange="NSE",
        transaction_type="SELL",
        quantity=1,
        condition="",
    )
    await service.update_rule(rule2.id, is_active=False)

    active = await service.list_rules(is_active=True)
    assert len(active) == 1
    assert active[0].name == "Active"


@pytest.mark.asyncio
async def test_get_rule(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    service = RuleEngineService(db_session, mock_redis)
    created = await service.create_rule(
        name="Test",
        tradingsymbol="INFY",
        exchange="NSE",
        transaction_type="BUY",
        quantity=5,
        condition="",
    )
    rule = await service.get_rule(created.id)
    assert rule is not None
    assert rule.tradingsymbol == "INFY"


@pytest.mark.asyncio
async def test_update_rule(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    service = RuleEngineService(db_session, mock_redis)
    rule = await service.create_rule(
        name="Original",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        condition="",
    )
    updated = await service.update_rule(rule.id, name="Updated", quantity=10)
    assert updated is not None
    assert updated.name == "Updated"
    assert updated.quantity == 10


@pytest.mark.asyncio
async def test_delete_rule(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    service = RuleEngineService(db_session, mock_redis)
    rule = await service.create_rule(
        name="To Delete",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        condition="",
    )
    deleted = await service.delete_rule(rule.id)
    assert deleted is True

    found = await service.get_rule(rule.id)
    assert found is None


# --- Condition Evaluation ---


def test_evaluate_price_above() -> None:
    assert RuleEngineService._evaluate_condition({"type": "price_above", "value": 2000}, 2500) is True
    assert RuleEngineService._evaluate_condition({"type": "price_above", "value": 3000}, 2500) is False


def test_evaluate_price_below() -> None:
    assert RuleEngineService._evaluate_condition({"type": "price_below", "value": 3000}, 2500) is True
    assert RuleEngineService._evaluate_condition({"type": "price_below", "value": 2000}, 2500) is False


def test_evaluate_price_drop_pct() -> None:
    condition = {"type": "price_drop_pct", "value": 5.0, "reference_price": 1000}
    # 10% drop: (1000-900)/1000 = 10% >= 5%
    assert RuleEngineService._evaluate_condition(condition, 900) is True
    # 2% drop: not enough
    assert RuleEngineService._evaluate_condition(condition, 980) is False


def test_evaluate_empty_condition() -> None:
    assert RuleEngineService._evaluate_condition({}, 100) is False
    assert RuleEngineService._evaluate_condition({"type": "unknown", "value": 100}, 100) is False


# --- Rule Evaluation with DB ---


@pytest.mark.asyncio
async def test_evaluate_rules_triggers(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=True)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())

    # Add a trade so price lookup works from DB
    db_session.add(
        Trade(
            order_id="t1",
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            price=1500.0,
            product="CNC",
            order_type="MARKET",
            status="COMPLETE",
        )
    )
    await db_session.commit()

    service = RuleEngineService(db_session, mock_redis)
    await service.create_rule(
        name="Buy dip",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        condition=json.dumps({"type": "price_below", "value": 2000}),
    )

    with patch.object(service, "_execute_rule") as mock_exec:
        from app.schemas.order import OrderPlaceResponse

        mock_exec.return_value = OrderPlaceResponse(order_id="DRY_RUN", status="SUCCESS", dry_run=True, risk_checks=[])
        results = await service.evaluate_rules()

    assert len(results) == 1
    assert results[0]["triggered"] is True


@pytest.mark.asyncio
async def test_evaluate_rules_no_trigger(db_session: AsyncSession, mock_redis: AsyncMock) -> None:
    config = SafetyConfig(dry_run=True)
    mock_redis.get = AsyncMock(return_value=config.model_dump_json())

    db_session.add(
        Trade(
            order_id="t1",
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            price=3000.0,
            product="CNC",
            order_type="MARKET",
            status="COMPLETE",
        )
    )
    await db_session.commit()

    service = RuleEngineService(db_session, mock_redis)
    await service.create_rule(
        name="Buy dip",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        condition=json.dumps({"type": "price_below", "value": 2000}),
    )

    results = await service.evaluate_rules()
    assert len(results) == 1
    assert results[0]["triggered"] is False
