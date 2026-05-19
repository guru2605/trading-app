import client from "./client";
import type {
  Alert,
  AlertCheckResponse,
  AlertCreateRequest,
  AlertUpdateRequest,
} from "../types/trade";

export async function fetchAlerts(
  is_active?: boolean
): Promise<Alert[]> {
  const { data } = await client.get<Alert[]>("/alerts", {
    params: is_active !== undefined ? { is_active } : undefined,
  });
  return data;
}

export async function createAlert(
  req: AlertCreateRequest
): Promise<Alert> {
  const { data } = await client.post<Alert>("/alerts", req);
  return data;
}

export async function updateAlert(
  id: number,
  req: AlertUpdateRequest
): Promise<Alert> {
  const { data } = await client.put<Alert>(`/alerts/${id}`, req);
  return data;
}

export async function deleteAlert(id: number): Promise<void> {
  await client.delete(`/alerts/${id}`);
}

export async function checkAlerts(): Promise<AlertCheckResponse> {
  const { data } = await client.post<AlertCheckResponse>("/alerts/check");
  return data;
}
