export interface Holding {
  id: number;
  tradingsymbol: string;
  exchange: string;
  isin: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  day_change: number;
  day_change_pct: number;
  weight: number;
  synced_at: string;
}

export interface Position {
  tradingsymbol: string;
  exchange: string;
  product: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  day_buy_quantity: number;
  day_sell_quantity: number;
  buy_value: number;
  sell_value: number;
}

export interface Order {
  order_id: string;
  tradingsymbol: string;
  exchange: string;
  transaction_type: string;
  order_type: string;
  product: string;
  quantity: number;
  price: number;
  trigger_price: number;
  status: string;
  filled_quantity: number;
  average_price: number;
  order_timestamp: string | null;
}

export interface PortfolioSummary {
  total_invested: number;
  total_current: number;
  total_pnl: number;
  total_pnl_pct: number;
  day_pnl: number;
  day_pnl_pct: number;
  holdings_count: number;
}

export interface AllocationItem {
  sector: string;
  value: number;
  weight: number;
  holdings_count: number;
}

export interface AllocationResponse {
  allocations: AllocationItem[];
  total_value: number;
}

export interface CorrelationPair {
  stock_a: string;
  stock_b: string;
  correlation: number;
}

export interface CorrelationResponse {
  symbols: string[];
  matrix: number[][];
  high_correlations: CorrelationPair[];
  warnings: string[];
}

export interface ExposureResponse {
  total_exposure: number;
  net_exposure: number;
  long_exposure: number;
  short_exposure: number;
  leverage: number;
  directional_bias: string;
}

export interface SyncResponse {
  synced: number;
  message: string;
}
