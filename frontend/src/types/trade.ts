export interface Trade {
  id: number;
  order_id: string;
  exchange_order_id: string;
  tradingsymbol: string;
  exchange: string;
  transaction_type: string;
  quantity: number;
  price: number;
  product: string;
  order_type: string;
  status: string;
  traded_at: string | null;
  created_at: string;
}

export interface TradeSyncResponse {
  synced: number;
  message: string;
}

export interface RiskSnapshot {
  id: number;
  snapshot_date: string;
  total_invested: number;
  total_current: number;
  total_pnl: number;
  day_pnl: number;
  max_single_stock_pct: number;
  sector_concentration: Record<string, number>;
  details: Record<string, unknown>;
  created_at: string;
}

export interface RiskSnapshotCreateResponse {
  id: number;
  snapshot_date: string;
  message: string;
}

export interface Alert {
  id: number;
  tradingsymbol: string;
  exchange: string;
  alert_type: string;
  target_value: number;
  is_active: boolean;
  triggered_at: string | null;
  created_at: string;
}

export interface AlertCreateRequest {
  tradingsymbol: string;
  exchange?: string;
  alert_type: string;
  target_value: number;
}

export interface AlertUpdateRequest {
  target_value?: number;
  is_active?: boolean;
}

export interface AlertCheckResult {
  tradingsymbol: string;
  alert_type: string;
  target_value: number;
  current_price: number;
  triggered: boolean;
}

export interface AlertCheckResponse {
  checked: number;
  triggered: number;
  results: AlertCheckResult[];
}
