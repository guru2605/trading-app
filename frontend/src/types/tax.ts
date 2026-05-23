export interface TaxLot {
  id: number;
  tradingsymbol: string;
  exchange: string;
  buy_date: string;
  buy_price: number;
  quantity: number;
  remaining_quantity: number;
  sell_date: string | null;
  sell_price: number | null;
  realized_pnl: number | null;
  holding_type: string;
  created_at: string;
}

export interface TaxSummary {
  total_stcg: number;
  total_ltcg: number;
  total_intraday: number;
  total_fno: number;
  estimated_stcg_tax: number;
  estimated_ltcg_tax: number;
  fy: string;
}

export interface DailyTaxEstimate {
  date: string;
  stcg_to_date: number;
  ltcg_to_date: number;
  intraday_to_date: number;
  fno_to_date: number;
  estimated_tax: number;
  advance_tax_due: number;
}

export interface WashSale {
  tradingsymbol: string;
  sell_date: string;
  sell_price: number;
  rebuy_date: string;
  rebuy_price: number;
  loss_amount: number;
}

export interface TaxComputeResponse {
  lots_created: number;
  lots_updated: number;
  message: string;
}
