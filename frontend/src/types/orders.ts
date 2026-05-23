export interface RiskCheckResult {
  stage: string;
  passed: boolean;
  reason: string;
}

export interface OrderPlaceRequest {
  tradingsymbol: string;
  exchange?: string;
  transaction_type: string;
  quantity: number;
  price?: number | null;
  product?: string;
  order_type?: string;
  trigger_price?: number | null;
}

export interface OrderPlaceResponse {
  order_id: string | null;
  status: string;
  dry_run: boolean;
  risk_checks: RiskCheckResult[];
}

export interface OrderMarginResponse {
  total: number;
  available: number | null;
  sufficient: boolean;
}

export interface OrderRule {
  id: number;
  name: string;
  tradingsymbol: string;
  exchange: string;
  transaction_type: string;
  quantity: number;
  price: number | null;
  trigger_price: number | null;
  product: string;
  order_type: string;
  condition: string;
  is_active: boolean;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrderRuleCreateRequest {
  name: string;
  tradingsymbol: string;
  exchange?: string;
  transaction_type?: string;
  quantity?: number;
  price?: number | null;
  trigger_price?: number | null;
  product?: string;
  order_type?: string;
  condition?: string;
}

export interface SafetyConfig {
  panic_mode: boolean;
  max_daily_loss: number;
  max_order_value: number;
  max_orders_per_day: number;
  max_position_pct: number;
  loss_cooldown_count: number;
  loss_cooldown_minutes: number;
  vix_kill_threshold: number;
  dry_run: boolean;
}

export interface SafetyStatusResponse {
  config: SafetyConfig;
  panic_active: boolean;
  cooldown_active: boolean;
  trading_hours_active: boolean;
  orders_today: number;
  realized_pnl_today: number;
}

export interface RuleEvaluateResult {
  rule_id: number;
  name: string;
  triggered: boolean;
  current_price?: number;
  order_status?: string;
  reason?: string;
}
