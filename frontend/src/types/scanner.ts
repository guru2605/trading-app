export interface WatchlistItem {
  id: number;
  tradingsymbol: string;
  exchange: string;
  notes: string;
  added_at: string;
}

export interface WatchlistItemCreateRequest {
  tradingsymbol: string;
  exchange?: string;
  notes?: string;
}

export interface Signal {
  id: number;
  tradingsymbol: string;
  exchange: string;
  signal_type: string;
  timeframe: string;
  entry_price: number;
  stop_loss: number;
  target_price: number;
  confidence: number;
  indicators: Record<string, unknown>;
  rationale: string;
  status: string;
  created_at: string;
  expired_at: string | null;
}

export interface SignalUpdateRequest {
  status: string;
}

export interface ScanRequest {
  timeframe?: string;
}

export interface ScanResultItem {
  tradingsymbol: string;
  exchange: string;
  signal_type: string;
  entry_price: number;
  stop_loss: number;
  target_price: number;
  confidence: number;
  rationale: string;
}

export interface ScanResponse {
  scanned: number;
  signals_generated: number;
  results: ScanResultItem[];
  errors: string[];
}

export interface InstrumentSearchResult {
  tradingsymbol: string;
  name: string;
  exchange: string;
}
