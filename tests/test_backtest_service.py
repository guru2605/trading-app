"""Tests for BacktestService."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.backtest import BacktestResult, BacktestService, Trade


def _make_candles(n: int, base_price: float = 100.0, trend: str = "up") -> list[dict[str, Any]]:
    """Generate synthetic candle data."""
    candles: list[dict[str, Any]] = []
    price = base_price
    start = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(n):
        if trend == "up":
            price *= 1 + random.uniform(0.001, 0.02)
        elif trend == "down":
            price *= 1 - random.uniform(0.001, 0.02)
        else:
            price *= 1 + random.uniform(-0.01, 0.01)
        candles.append(
            {
                "date": start + timedelta(days=i),
                "open": round(price * 0.998, 2),
                "high": round(price * 1.01, 2),
                "low": round(price * 0.99, 2),
                "close": round(price, 2),
                "volume": random.randint(100000, 500000),
            }
        )
    return candles


class TestTrade:
    def test_trade_defaults(self) -> None:
        trade = Trade(
            symbol="RELIANCE",
            signal_type="BUY",
            entry_bar=10,
            entry_price=2500.0,
            stop_loss=2450.0,
            target_price=2600.0,
            confidence=65.0,
        )
        assert trade.exit_bar is None
        assert trade.outcome is None
        assert trade.pnl_pct == 0.0


class TestBacktestResult:
    def test_default_result(self) -> None:
        result = BacktestResult(symbol="INFY", timeframe="day")
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.trades == []


class TestBacktestService:
    @pytest.fixture
    def service(self) -> BacktestService:
        return BacktestService(max_hold_bars=10)

    async def test_run_insufficient_data(self, service: BacktestService) -> None:
        with patch.object(service.market_data, "fetch_historical", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_candles(20)
            result = await service.run("RELIANCE", lookback_bars=50)
        assert result.total_trades == 0
        assert result.symbol == "RELIANCE"

    async def test_run_empty_data(self, service: BacktestService) -> None:
        with patch.object(service.market_data, "fetch_historical", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            result = await service.run("RELIANCE")
        assert result.total_trades == 0

    async def test_run_with_data(self, service: BacktestService) -> None:
        candles = _make_candles(200, trend="up")
        with patch.object(service.market_data, "fetch_historical", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = candles
            result = await service.run("RELIANCE", lookback_bars=50)
        assert isinstance(result, BacktestResult)
        assert result.symbol == "RELIANCE"
        assert result.timeframe == "day"
        # May or may not generate trades depending on synthetic data
        assert result.total_trades >= 0
        assert result.wins + result.losses + result.expired == result.total_trades

    async def test_run_computes_metrics(self, service: BacktestService) -> None:
        """With enough data and a strong trend, verify metrics are computed."""
        candles = _make_candles(200, trend="up")
        with patch.object(service.market_data, "fetch_historical", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = candles
            result = await service.run("INFY", lookback_bars=50)
        if result.total_trades > 0:
            assert 0.0 <= result.win_rate <= 100.0
            assert isinstance(result.sharpe_ratio, float)
            assert isinstance(result.max_drawdown_pct, float)
            assert isinstance(result.profit_factor, float)

    async def test_compare_returns_both(self, service: BacktestService) -> None:
        candles = _make_candles(200, trend="up")
        with patch.object(service.market_data, "fetch_historical", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = candles
            with patch("app.services.backtest.MarketDataService") as mock_mds_cls:
                mock_instance = AsyncMock()
                mock_instance.fetch_historical = AsyncMock(return_value=candles)
                mock_mds_cls.return_value = mock_instance
                results = await service.compare("RELIANCE")
        assert "current" in results
        assert "proposed" in results
        assert isinstance(results["current"], BacktestResult)
        assert isinstance(results["proposed"], BacktestResult)

    def test_compute_pnl_pct_buy(self) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="BUY",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=95.0,
            target_price=110.0,
            confidence=60.0,
        )
        pnl = BacktestService._compute_pnl_pct(trade, 110.0)
        assert pnl == pytest.approx(10.0)

    def test_compute_pnl_pct_sell(self) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="SELL",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=105.0,
            target_price=90.0,
            confidence=60.0,
        )
        pnl = BacktestService._compute_pnl_pct(trade, 90.0)
        assert pnl == pytest.approx(10.0)

    def test_compute_rr(self) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="BUY",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=95.0,
            target_price=110.0,
            confidence=60.0,
            exit_price=110.0,
        )
        rr = BacktestService._compute_rr(trade)
        assert rr == pytest.approx(2.0)

    def test_compute_rr_loss(self) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="BUY",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=95.0,
            target_price=110.0,
            confidence=60.0,
            exit_price=95.0,
        )
        rr = BacktestService._compute_rr(trade)
        assert rr == pytest.approx(-1.0)

    def test_check_exit_buy_target(self, service: BacktestService) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="BUY",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=95.0,
            target_price=110.0,
            confidence=60.0,
        )
        exited = service._check_exit(trade, high=112.0, low=99.0, close=111.0, bar_idx=5, bars_held=5)
        assert exited is True
        assert trade.outcome == "win"
        assert trade.exit_price == 110.0

    def test_check_exit_buy_stop(self, service: BacktestService) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="BUY",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=95.0,
            target_price=110.0,
            confidence=60.0,
        )
        exited = service._check_exit(trade, high=99.0, low=93.0, close=94.0, bar_idx=3, bars_held=3)
        assert exited is True
        assert trade.outcome == "loss"
        assert trade.exit_price == 95.0

    def test_check_exit_sell_target(self, service: BacktestService) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="SELL",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=105.0,
            target_price=90.0,
            confidence=60.0,
        )
        exited = service._check_exit(trade, high=92.0, low=88.0, close=89.0, bar_idx=4, bars_held=4)
        assert exited is True
        assert trade.outcome == "win"
        assert trade.exit_price == 90.0

    def test_check_exit_expired(self, service: BacktestService) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="BUY",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=95.0,
            target_price=110.0,
            confidence=60.0,
        )
        exited = service._check_exit(trade, high=102.0, low=99.0, close=101.0, bar_idx=10, bars_held=10)
        assert exited is True
        assert trade.outcome == "expired"

    def test_check_exit_not_triggered(self, service: BacktestService) -> None:
        trade = Trade(
            symbol="TEST",
            signal_type="BUY",
            entry_bar=0,
            entry_price=100.0,
            stop_loss=95.0,
            target_price=110.0,
            confidence=60.0,
        )
        exited = service._check_exit(trade, high=102.0, low=99.0, close=101.0, bar_idx=3, bars_held=3)
        assert exited is False

    def test_compute_stop_loss_buy(self, service: BacktestService) -> None:
        sl = service._compute_stop_loss(100.0, 5.0, "BUY", {})
        assert sl == pytest.approx(92.5)  # 100 - 5*1.5

    def test_compute_target_buy(self, service: BacktestService) -> None:
        target = service._compute_target(100.0, 92.5, "BUY")
        assert target == pytest.approx(115.0)  # 100 + 7.5*2

    def test_compute_metrics_empty(self, service: BacktestService) -> None:
        result = service._compute_metrics([], "TEST", "day")
        assert result.total_trades == 0
        assert result.win_rate == 0.0

    def test_compute_metrics_with_trades(self, service: BacktestService) -> None:
        trades = [
            Trade(
                symbol="T",
                signal_type="BUY",
                entry_bar=0,
                entry_price=100.0,
                stop_loss=95.0,
                target_price=110.0,
                confidence=60.0,
                exit_bar=5,
                exit_price=110.0,
                outcome="win",
                pnl_pct=10.0,
                rr_achieved=2.0,
            ),
            Trade(
                symbol="T",
                signal_type="BUY",
                entry_bar=10,
                entry_price=100.0,
                stop_loss=95.0,
                target_price=110.0,
                confidence=55.0,
                exit_bar=13,
                exit_price=95.0,
                outcome="loss",
                pnl_pct=-5.0,
                rr_achieved=-1.0,
            ),
        ]
        result = service._compute_metrics(trades, "T", "day")
        assert result.total_trades == 2
        assert result.wins == 1
        assert result.losses == 1
        assert result.win_rate == 50.0
        assert result.total_return_pct == 5.0
        assert result.profit_factor == 2.0

    def test_candles_to_dataframe(self) -> None:
        candles = _make_candles(10)
        df = BacktestService._candles_to_dataframe(candles)
        assert len(df) == 10
        assert "close" in df.columns

    def test_candles_to_dataframe_empty(self) -> None:
        df = BacktestService._candles_to_dataframe([])
        assert df.empty
