from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade
from app.services.tax import TaxService, parse_fy

# ── Helpers ──────────────────────────────────────────────────────────────


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _buy_trade(symbol: str, qty: int, price: float, dt: datetime, product: str = "CNC") -> Trade:
    return Trade(
        order_id=f"B-{symbol}-{dt.date()}",
        tradingsymbol=symbol,
        exchange="NSE",
        transaction_type="BUY",
        quantity=qty,
        price=price,
        product=product,
        order_type="MARKET",
        status="COMPLETE",
        traded_at=dt,
    )


def _sell_trade(symbol: str, qty: int, price: float, dt: datetime, product: str = "CNC") -> Trade:
    return Trade(
        order_id=f"S-{symbol}-{dt.date()}",
        tradingsymbol=symbol,
        exchange="NSE",
        transaction_type="SELL",
        quantity=qty,
        price=price,
        product=product,
        order_type="MARKET",
        status="COMPLETE",
        traded_at=dt,
    )


# ── parse_fy ─────────────────────────────────────────────────────────────


def test_parse_fy_explicit() -> None:
    start, end = parse_fy("2025-2026")
    assert start == _dt(2025, 4, 1)
    assert end.year == 2026 and end.month == 3 and end.day == 31


def test_parse_fy_none_defaults() -> None:
    start, _ = parse_fy(None)
    assert start.month == 4 and start.day == 1


# ── FIFO matching ────────────────────────────────────────────────────────


async def test_compute_creates_buy_lots(db_session: AsyncSession) -> None:
    db_session.add(_buy_trade("INFY", 10, 1500.0, _dt(2025, 5, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    result = await service.compute_tax_lots("2025-2026")

    assert result.lots_created >= 1
    lots = await service.get_lots("2025-2026")
    assert len(lots) >= 1
    assert lots[0].tradingsymbol == "INFY"
    assert lots[0].remaining_quantity == 10


async def test_fifo_simple_full_match(db_session: AsyncSession) -> None:
    """Buy 10 shares, sell 10 shares -> one fully consumed lot."""
    db_session.add(_buy_trade("INFY", 10, 1500.0, _dt(2025, 5, 1)))
    db_session.add(_sell_trade("INFY", 10, 1600.0, _dt(2025, 8, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")

    lots = await service.get_lots("2025-2026")
    sold_lots = [lot for lot in lots if lot.sell_date is not None]
    assert len(sold_lots) == 1
    assert sold_lots[0].remaining_quantity == 0
    assert sold_lots[0].realized_pnl == 1000.0  # (1600-1500)*10
    assert sold_lots[0].holding_type == "STCG"


async def test_fifo_partial_match(db_session: AsyncSession) -> None:
    """Buy 10 shares, sell 4 shares -> split into sold lot (4) and remaining lot (6)."""
    db_session.add(_buy_trade("TCS", 10, 3000.0, _dt(2025, 5, 1)))
    db_session.add(_sell_trade("TCS", 4, 3200.0, _dt(2025, 7, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")

    lots = await service.get_lots("2025-2026")
    assert len(lots) >= 2  # original (6 remaining) + split sold (4)

    sold = [lot for lot in lots if lot.sell_date is not None]
    unsold = [lot for lot in lots if lot.sell_date is None]
    assert len(sold) == 1
    assert sold[0].quantity == 4
    assert sold[0].realized_pnl == 800.0  # (3200-3000)*4
    assert len(unsold) >= 1
    assert any(lot.remaining_quantity == 6 for lot in unsold)


async def test_fifo_multiple_buy_lots(db_session: AsyncSession) -> None:
    """Two buy lots consumed FIFO order."""
    db_session.add(_buy_trade("RELIANCE", 5, 2000.0, _dt(2025, 4, 10)))
    # Need a different order_id for the second buy
    t2 = _buy_trade("RELIANCE", 5, 2100.0, _dt(2025, 5, 10))
    t2.order_id = "B-RELIANCE-2025-05-10-2"
    db_session.add(t2)
    db_session.add(_sell_trade("RELIANCE", 8, 2200.0, _dt(2025, 9, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")

    lots = await service.get_lots("2025-2026")
    sold = [lot for lot in lots if lot.sell_date is not None]
    total_pnl = sum(lot.realized_pnl or 0 for lot in sold)
    # First 5 shares: (2200-2000)*5 = 1000, next 3 shares: (2200-2100)*3 = 300
    assert total_pnl == pytest.approx(1300.0)


# ── STCG / LTCG classification ──────────────────────────────────────────


async def test_ltcg_classification(db_session: AsyncSession) -> None:
    """Holding > 365 days -> LTCG."""
    db_session.add(_buy_trade("HDFC", 10, 1000.0, _dt(2024, 4, 1)))
    db_session.add(_sell_trade("HDFC", 10, 1200.0, _dt(2025, 6, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")

    lots = await service.get_lots("2025-2026")
    sold = [lot for lot in lots if lot.sell_date is not None]
    assert len(sold) == 1
    assert sold[0].holding_type == "LTCG"


async def test_stcg_classification(db_session: AsyncSession) -> None:
    """Holding <= 365 days -> STCG."""
    db_session.add(_buy_trade("SBIN", 10, 500.0, _dt(2025, 5, 1)))
    db_session.add(_sell_trade("SBIN", 10, 550.0, _dt(2025, 8, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")

    lots = await service.get_lots("2025-2026")
    sold = [lot for lot in lots if lot.sell_date is not None]
    assert len(sold) == 1
    assert sold[0].holding_type == "STCG"


async def test_intraday_classification_mis(db_session: AsyncSession) -> None:
    """MIS product -> INTRADAY."""
    db_session.add(_buy_trade("WIPRO", 10, 400.0, _dt(2025, 5, 1), product="MIS"))
    db_session.add(_sell_trade("WIPRO", 10, 410.0, _dt(2025, 5, 1), product="MIS"))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")

    lots = await service.get_lots("2025-2026")
    sold = [lot for lot in lots if lot.sell_date is not None]
    assert len(sold) == 1
    assert sold[0].holding_type == "INTRADAY"


async def test_fno_classification(db_session: AsyncSession) -> None:
    """NRML product -> FNO."""
    db_session.add(_buy_trade("NIFTY25JUNFUT", 50, 22000.0, _dt(2025, 5, 1), product="NRML"))
    db_session.add(_sell_trade("NIFTY25JUNFUT", 50, 22100.0, _dt(2025, 5, 15), product="NRML"))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")

    lots = await service.get_lots("2025-2026")
    sold = [lot for lot in lots if lot.sell_date is not None]
    assert len(sold) == 1
    assert sold[0].holding_type == "FNO"


# ── Summary ──────────────────────────────────────────────────────────────


async def test_summary_computation(db_session: AsyncSession) -> None:
    # STCG trade
    db_session.add(_buy_trade("INFY", 10, 1500.0, _dt(2025, 5, 1)))
    db_session.add(_sell_trade("INFY", 10, 1600.0, _dt(2025, 8, 1)))
    # LTCG trade
    db_session.add(_buy_trade("TCS", 10, 3000.0, _dt(2024, 4, 1)))
    db_session.add(_sell_trade("TCS", 10, 3500.0, _dt(2025, 6, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")
    summary = await service.get_summary("2025-2026")

    assert summary.fy == "2025-2026"
    assert summary.total_stcg == 1000.0  # (1600-1500)*10
    assert summary.total_ltcg == 5000.0  # (3500-3000)*10
    assert summary.estimated_stcg_tax == 200.0  # 1000 * 0.20
    # LTCG: (5000 - 125000) < 0 -> tax = 0
    assert summary.estimated_ltcg_tax == 0.0


async def test_summary_ltcg_above_exemption(db_session: AsyncSession) -> None:
    """LTCG above 1.25L exemption should be taxed at 12.5%."""
    # Large LTCG trade: buy at 1000, sell at 2500, qty=100 -> pnl=150000
    db_session.add(_buy_trade("HDFCBANK", 100, 1000.0, _dt(2024, 1, 1)))
    db_session.add(_sell_trade("HDFCBANK", 100, 2500.0, _dt(2025, 6, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")
    summary = await service.get_summary("2025-2026")

    assert summary.total_ltcg == 150000.0
    # (150000 - 125000) * 0.125 = 3125.0
    assert summary.estimated_ltcg_tax == 3125.0


# ── Wash sales ───────────────────────────────────────────────────────────


async def test_wash_sale_detected(db_session: AsyncSession) -> None:
    """Sell at a loss, rebuy within 30 days -> wash sale advisory."""
    db_session.add(_buy_trade("INFY", 10, 1500.0, _dt(2025, 5, 1)))
    db_session.add(_sell_trade("INFY", 10, 1400.0, _dt(2025, 7, 1)))
    # Rebuy within 30 days
    rebuy = _buy_trade("INFY", 10, 1350.0, _dt(2025, 7, 15))
    rebuy.order_id = "B-INFY-2025-07-15"
    db_session.add(rebuy)
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")
    wash_sales = await service.detect_wash_sales("2025-2026")

    assert len(wash_sales) == 1
    assert wash_sales[0].tradingsymbol == "INFY"
    assert wash_sales[0].loss_amount == 1000.0  # (1500-1400)*10


async def test_no_wash_sale_after_30_days(db_session: AsyncSession) -> None:
    """Rebuy after 30 days -> no wash sale."""
    db_session.add(_buy_trade("INFY", 10, 1500.0, _dt(2025, 5, 1)))
    db_session.add(_sell_trade("INFY", 10, 1400.0, _dt(2025, 7, 1)))
    # Rebuy after 30 days
    rebuy = _buy_trade("INFY", 10, 1350.0, _dt(2025, 8, 5))
    rebuy.order_id = "B-INFY-2025-08-05"
    db_session.add(rebuy)
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")
    wash_sales = await service.detect_wash_sales("2025-2026")

    assert len(wash_sales) == 0


# ── CSV generation ───────────────────────────────────────────────────────


async def test_csv_generation(db_session: AsyncSession) -> None:
    db_session.add(_buy_trade("INFY", 10, 1500.0, _dt(2025, 5, 1)))
    db_session.add(_sell_trade("INFY", 10, 1600.0, _dt(2025, 8, 1)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")
    csv_str = await service.generate_csv("2025-2026")

    assert "Tradingsymbol" in csv_str
    assert "INFY" in csv_str
    assert "1500" in csv_str
    lines = csv_str.strip().split("\n")
    assert len(lines) >= 2  # header + at least 1 data row


# ── Daily estimate ───────────────────────────────────────────────────────


async def test_daily_estimate(db_session: AsyncSession) -> None:
    db_session.add(_buy_trade("INFY", 10, 1500.0, _dt(2025, 5, 1)))
    db_session.add(_sell_trade("INFY", 10, 1600.0, _dt(2025, 5, 15)))
    await db_session.commit()

    service = TaxService(db_session)
    await service.compute_tax_lots("2025-2026")
    estimates = await service.get_daily_estimate("2025-2026")

    assert len(estimates) >= 1
    assert estimates[0].stcg_to_date == 1000.0
    assert estimates[0].estimated_tax > 0
    assert estimates[0].advance_tax_due > 0
