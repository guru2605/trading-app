import client from "./client";
import type {
  AllocationResponse,
  CorrelationResponse,
  ExposureResponse,
  Holding,
  Order,
  PortfolioSummary,
  Position,
  SyncResponse,
} from "../types/portfolio";

export async function fetchHoldings(): Promise<Holding[]> {
  const { data } = await client.get<Holding[]>("/portfolio/holdings");
  return data;
}

export async function fetchPositions(): Promise<Position[]> {
  const { data } = await client.get<Position[]>("/portfolio/positions");
  return data;
}

export async function fetchOrders(): Promise<Order[]> {
  const { data } = await client.get<Order[]>("/portfolio/orders");
  return data;
}

export async function fetchSummary(): Promise<PortfolioSummary> {
  const { data } = await client.get<PortfolioSummary>("/portfolio/summary");
  return data;
}

export async function fetchAllocation(): Promise<AllocationResponse> {
  const { data } = await client.get<AllocationResponse>(
    "/portfolio/allocation"
  );
  return data;
}

export async function fetchCorrelation(): Promise<CorrelationResponse> {
  const { data } = await client.get<CorrelationResponse>(
    "/portfolio/correlation"
  );
  return data;
}

export async function fetchExposure(): Promise<ExposureResponse> {
  const { data } = await client.get<ExposureResponse>("/portfolio/exposure");
  return data;
}

export async function syncHoldings(): Promise<SyncResponse> {
  const { data } = await client.post<SyncResponse>("/portfolio/sync");
  return data;
}
