export interface JournalEntry {
  id: number;
  trade_id: number | null;
  tradingsymbol: string;
  entry_type: string;
  content: string;
  tags: string;
  strategy: string;
  outcome: string;
  emotional_state: string;
  created_at: string;
  updated_at: string;
}

export interface JournalCreateRequest {
  tradingsymbol: string;
  entry_type: string;
  content?: string;
  tags?: string;
  strategy?: string;
  outcome?: string;
  emotional_state?: string;
  trade_id?: number | null;
}

export interface JournalUpdateRequest {
  tradingsymbol?: string;
  entry_type?: string;
  content?: string;
  tags?: string;
  strategy?: string;
  outcome?: string;
  emotional_state?: string;
  trade_id?: number | null;
}

export interface StrategyStats {
  strategy: string;
  count: number;
  wins: number;
  losses: number;
  win_rate: number;
}

export interface TagStats {
  tag: string;
  count: number;
}

export interface JournalAnalytics {
  total_entries: number;
  win_rate: number;
  total_wins: number;
  total_losses: number;
  total_breakeven: number;
  by_strategy: StrategyStats[];
  by_tag: TagStats[];
}

export interface BehaviorFlag {
  id: number;
  flag_type: string;
  severity: string;
  description: string;
  trade_id: number | null;
  is_acknowledged: boolean;
  created_at: string;
}

export interface BehaviorDetectionResponse {
  flags: BehaviorFlag[];
  summary: string;
}

export interface BehaviorSummary {
  total: number;
  by_severity: Record<string, number>;
  unacknowledged: number;
  recent_flags: BehaviorFlag[];
}
