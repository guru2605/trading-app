import client from "./client";
import type {
  InstrumentSearchResult,
  ScanRequest,
  ScanResponse,
  Signal,
  SignalUpdateRequest,
  WatchlistItem,
  WatchlistItemCreateRequest,
} from "../types/scanner";

export async function fetchWatchlist(): Promise<WatchlistItem[]> {
  const { data } = await client.get<WatchlistItem[]>("/watchlist");
  return data;
}

export async function addToWatchlist(
  req: WatchlistItemCreateRequest,
): Promise<WatchlistItem> {
  const { data } = await client.post<WatchlistItem>("/watchlist", req);
  return data;
}

export async function removeFromWatchlist(id: number): Promise<void> {
  await client.delete(`/watchlist/${id}`);
}

export async function runScan(req?: ScanRequest): Promise<ScanResponse> {
  const { data } = await client.post<ScanResponse>("/scanner/scan", req ?? {});
  return data;
}

export async function fetchSignals(params?: {
  status?: string;
  signal_type?: string;
  tradingsymbol?: string;
}): Promise<Signal[]> {
  const { data } = await client.get<Signal[]>("/signals", { params });
  return data;
}

export async function getSignal(id: number): Promise<Signal> {
  const { data } = await client.get<Signal>(`/signals/${id}`);
  return data;
}

export async function updateSignalStatus(
  id: number,
  req: SignalUpdateRequest,
): Promise<Signal> {
  const { data } = await client.put<Signal>(`/signals/${id}`, req);
  return data;
}

export async function importFromHoldings(): Promise<{
  added: number;
  message: string;
}> {
  const { data } = await client.post<{ added: number; message: string }>(
    "/watchlist/import-holdings",
  );
  return data;
}

export async function searchInstruments(
  q: string,
  exchange: string = "NSE",
): Promise<InstrumentSearchResult[]> {
  const { data } = await client.get<InstrumentSearchResult[]>(
    "/watchlist/search-instruments",
    { params: { q, exchange } },
  );
  return data;
}
