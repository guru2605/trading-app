from pydantic import BaseModel


class SafetyConfig(BaseModel):
    panic_mode: bool = False
    max_daily_loss: float = 10000.0
    max_order_value: float = 50000.0
    max_orders_per_day: int = 10
    max_position_pct: float = 20.0
    loss_cooldown_count: int = 3
    loss_cooldown_minutes: int = 30
    vix_kill_threshold: float = 25.0
    dry_run: bool = True


class SafetyStatusResponse(BaseModel):
    config: SafetyConfig
    panic_active: bool
    cooldown_active: bool
    trading_hours_active: bool
    orders_today: int
    realized_pnl_today: float


class RiskCheckResult(BaseModel):
    stage: str
    passed: bool
    reason: str


class PanicResponse(BaseModel):
    panic_mode: bool
    message: str
