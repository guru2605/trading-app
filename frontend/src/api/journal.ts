import client from "./client";
import type {
  BehaviorDetectionResponse,
  BehaviorFlag,
  BehaviorSummary,
  JournalAnalytics,
  JournalCreateRequest,
  JournalEntry,
  JournalUpdateRequest,
} from "../types/journal";

export async function fetchJournalEntries(params?: {
  tradingsymbol?: string;
  entry_type?: string;
  trade_id?: number;
}): Promise<JournalEntry[]> {
  const { data } = await client.get<JournalEntry[]>("/journal", { params });
  return data;
}

export async function createJournalEntry(
  req: JournalCreateRequest,
): Promise<JournalEntry> {
  const { data } = await client.post<JournalEntry>("/journal", req);
  return data;
}

export async function updateJournalEntry(
  id: number,
  req: JournalUpdateRequest,
): Promise<JournalEntry> {
  const { data } = await client.put<JournalEntry>(`/journal/${id}`, req);
  return data;
}

export async function deleteJournalEntry(id: number): Promise<void> {
  await client.delete(`/journal/${id}`);
}

export async function fetchAnalytics(): Promise<JournalAnalytics> {
  const { data } = await client.get<JournalAnalytics>("/journal/analytics");
  return data;
}

export async function fetchBehaviorFlags(params?: {
  flag_type?: string;
  severity?: string;
  is_acknowledged?: boolean;
}): Promise<BehaviorFlag[]> {
  const { data } = await client.get<BehaviorFlag[]>("/behavior/flags", {
    params,
  });
  return data;
}

export async function runBehaviorDetection(): Promise<BehaviorDetectionResponse> {
  const { data } = await client.post<BehaviorDetectionResponse>(
    "/behavior/detect",
  );
  return data;
}

export async function acknowledgeBehaviorFlag(
  id: number,
  is_acknowledged: boolean,
): Promise<BehaviorFlag> {
  const { data } = await client.put<BehaviorFlag>(
    `/behavior/flags/${id}/acknowledge`,
    { is_acknowledged },
  );
  return data;
}

export async function fetchBehaviorSummary(): Promise<BehaviorSummary> {
  const { data } = await client.get<BehaviorSummary>("/behavior/summary");
  return data;
}
