import client from "./client";
import type {
  RiskSnapshot,
  RiskSnapshotCreateResponse,
  Trade,
  TradeSyncResponse,
} from "../types/trade";

export async function fetchTrades(params?: {
  tradingsymbol?: string;
  transaction_type?: string;
  limit?: number;
}): Promise<Trade[]> {
  const { data } = await client.get<Trade[]>("/trades", { params });
  return data;
}

export async function syncTrades(): Promise<TradeSyncResponse> {
  const { data } = await client.post<TradeSyncResponse>("/trades/sync");
  return data;
}

export async function fetchSnapshots(limit?: number): Promise<RiskSnapshot[]> {
  const { data } = await client.get<RiskSnapshot[]>("/risk/snapshots", {
    params: limit ? { limit } : undefined,
  });
  return data;
}

export async function fetchLatestSnapshot(): Promise<RiskSnapshot | null> {
  const { data } = await client.get<RiskSnapshot | null>(
    "/risk/snapshots/latest"
  );
  return data;
}

export async function createSnapshot(): Promise<RiskSnapshotCreateResponse> {
  const { data } = await client.post<RiskSnapshotCreateResponse>(
    "/risk/snapshots"
  );
  return data;
}
