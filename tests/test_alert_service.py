from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.alert import AlertService


async def test_create_alert(db_session: AsyncSession) -> None:
    service = AlertService(db_session)
    alert = await service.create_alert(
        tradingsymbol="RELIANCE",
        exchange="NSE",
        alert_type="price_above",
        target_value=3000.0,
    )

    assert alert.id is not None
    assert alert.tradingsymbol == "RELIANCE"
    assert alert.alert_type == "price_above"
    assert alert.target_value == 3000.0
    assert alert.is_active is True


async def test_list_alerts(db_session: AsyncSession) -> None:
    service = AlertService(db_session)
    await service.create_alert("INFY", "NSE", "price_above", 2000.0)
    await service.create_alert("TCS", "NSE", "price_below", 3000.0)

    alerts = await service.list_alerts()
    assert len(alerts) == 2


async def test_list_alerts_filter_active(db_session: AsyncSession) -> None:
    service = AlertService(db_session)
    alert = await service.create_alert("INFY", "NSE", "price_above", 2000.0)
    await service.create_alert("TCS", "NSE", "price_below", 3000.0)

    # Deactivate one
    await service.update_alert(alert.id, is_active=False)

    active = await service.list_alerts(is_active=True)
    assert len(active) == 1
    assert active[0].tradingsymbol == "TCS"


async def test_update_alert(db_session: AsyncSession) -> None:
    service = AlertService(db_session)
    alert = await service.create_alert("INFY", "NSE", "price_above", 2000.0)

    updated = await service.update_alert(alert.id, target_value=2500.0)
    assert updated is not None
    assert updated.target_value == 2500.0


async def test_update_nonexistent_alert(db_session: AsyncSession) -> None:
    service = AlertService(db_session)
    result = await service.update_alert(9999, target_value=100.0)
    assert result is None


async def test_delete_alert(db_session: AsyncSession) -> None:
    service = AlertService(db_session)
    alert = await service.create_alert("INFY", "NSE", "price_above", 2000.0)

    deleted = await service.delete_alert(alert.id)
    assert deleted is True

    alerts = await service.list_alerts()
    assert len(alerts) == 0


async def test_delete_nonexistent_alert(db_session: AsyncSession) -> None:
    service = AlertService(db_session)
    deleted = await service.delete_alert(9999)
    assert deleted is False


async def test_check_alerts_price_above_triggered(db_session: AsyncSession) -> None:
    mock_kite = AsyncMock()
    mock_kite.ltp.return_value = {
        "NSE:RELIANCE": {"last_price": 3100.0},
    }

    service = AlertService(db_session, mock_kite)
    await service.create_alert("RELIANCE", "NSE", "price_above", 3000.0)

    results = await service.check_alerts()
    assert len(results) == 1
    assert results[0].triggered is True
    assert results[0].current_price == 3100.0

    # Alert should be deactivated
    alerts = await service.list_alerts(is_active=True)
    assert len(alerts) == 0


async def test_check_alerts_price_below_triggered(db_session: AsyncSession) -> None:
    mock_kite = AsyncMock()
    mock_kite.ltp.return_value = {
        "NSE:INFY": {"last_price": 1400.0},
    }

    service = AlertService(db_session, mock_kite)
    await service.create_alert("INFY", "NSE", "price_below", 1500.0)

    results = await service.check_alerts()
    assert len(results) == 1
    assert results[0].triggered is True


async def test_check_alerts_not_triggered(db_session: AsyncSession) -> None:
    mock_kite = AsyncMock()
    mock_kite.ltp.return_value = {
        "NSE:RELIANCE": {"last_price": 2900.0},
    }

    service = AlertService(db_session, mock_kite)
    await service.create_alert("RELIANCE", "NSE", "price_above", 3000.0)

    results = await service.check_alerts()
    assert len(results) == 1
    assert results[0].triggered is False

    # Alert should still be active
    alerts = await service.list_alerts(is_active=True)
    assert len(alerts) == 1


async def test_check_alerts_requires_kite(db_session: AsyncSession) -> None:
    service = AlertService(db_session)
    await service.create_alert("INFY", "NSE", "price_above", 2000.0)

    with pytest.raises(RuntimeError, match="Kite client required"):
        await service.check_alerts()


async def test_check_alerts_empty(db_session: AsyncSession) -> None:
    mock_kite = AsyncMock()
    service = AlertService(db_session, mock_kite)

    results = await service.check_alerts()
    assert len(results) == 0
    mock_kite.ltp.assert_not_called()
