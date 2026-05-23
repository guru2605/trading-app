import client from "./client";
import type {
  DailyTaxEstimate,
  TaxComputeResponse,
  TaxLot,
  TaxSummary,
  WashSale,
} from "../types/tax";

export async function fetchTaxSummary(fy?: string): Promise<TaxSummary> {
  const { data } = await client.get<TaxSummary>("/tax/summary", {
    params: fy ? { fy } : undefined,
  });
  return data;
}

export async function fetchTaxLots(params?: {
  fy?: string;
  tradingsymbol?: string;
  holding_type?: string;
}): Promise<TaxLot[]> {
  const { data } = await client.get<TaxLot[]>("/tax/lots", { params });
  return data;
}

export async function fetchWashSales(fy?: string): Promise<WashSale[]> {
  const { data } = await client.get<WashSale[]>("/tax/wash-sales", {
    params: fy ? { fy } : undefined,
  });
  return data;
}

export async function fetchDailyEstimate(
  fy?: string
): Promise<DailyTaxEstimate[]> {
  const { data } = await client.get<DailyTaxEstimate[]>("/tax/daily", {
    params: fy ? { fy } : undefined,
  });
  return data;
}

export async function computeTaxLots(
  fy?: string
): Promise<TaxComputeResponse> {
  const { data } = await client.post<TaxComputeResponse>("/tax/compute", null, {
    params: fy ? { fy } : undefined,
  });
  return data;
}

export function downloadTaxReport(fy?: string): void {
  const params = fy ? `?fy=${fy}` : "";
  window.open(`/api/tax/report/download${params}`, "_blank");
}
