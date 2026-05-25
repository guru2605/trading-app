from fastapi import APIRouter
from pydantic import BaseModel

from app.services.backtest import BacktestService

router = APIRouter(prefix="/api", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    timeframe: str = "day"
    lookback_bars: int = 50
    max_hold_bars: int = 20


class TradeResponse(BaseModel):
    symbol: str
    signal_type: str
    entry_bar: int
    entry_price: float
    stop_loss: float
    target_price: float
    confidence: float
    exit_bar: int | None = None
    exit_price: float | None = None
    outcome: str | None = None
    pnl_pct: float = 0.0
    rr_achieved: float = 0.0


class BacktestResponse(BaseModel):
    symbol: str
    timeframe: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0
    win_rate: float = 0.0
    avg_rr: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    trades: list[TradeResponse] = []


class CompareResponse(BaseModel):
    current: BacktestResponse
    proposed: BacktestResponse


@router.post("/backtest/run", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest) -> BacktestResponse:
    service = BacktestService(max_hold_bars=req.max_hold_bars)
    result = await service.run(
        symbol=req.symbol,
        exchange=req.exchange,
        timeframe=req.timeframe,
        lookback_bars=req.lookback_bars,
    )
    return BacktestResponse(
        symbol=result.symbol,
        timeframe=result.timeframe,
        total_trades=result.total_trades,
        wins=result.wins,
        losses=result.losses,
        expired=result.expired,
        win_rate=result.win_rate,
        avg_rr=result.avg_rr,
        total_return_pct=result.total_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        sharpe_ratio=result.sharpe_ratio,
        profit_factor=result.profit_factor,
        trades=[TradeResponse(**t.__dict__) for t in result.trades],
    )
