import client from "./client";
import type {
  OrderPlaceRequest,
  OrderPlaceResponse,
  OrderMarginResponse,
  OrderRule,
  OrderRuleCreateRequest,
  SafetyConfig,
  SafetyStatusResponse,
  RuleEvaluateResult,
} from "../types/orders";

// Orders
export async function placeOrder(
  req: OrderPlaceRequest,
): Promise<OrderPlaceResponse> {
  const { data } = await client.post<OrderPlaceResponse>("/orders/place", req);
  return data;
}

export async function cancelOrder(orderId: string): Promise<void> {
  await client.delete(`/orders/${orderId}`);
}

export async function checkMargins(
  req: OrderPlaceRequest,
): Promise<OrderMarginResponse> {
  const { data } = await client.post<OrderMarginResponse>(
    "/orders/margins",
    req,
  );
  return data;
}

// Rules
export async function fetchRules(
  is_active?: boolean,
): Promise<OrderRule[]> {
  const { data } = await client.get<OrderRule[]>("/rules", {
    params: is_active !== undefined ? { is_active } : undefined,
  });
  return data;
}

export async function createRule(
  req: OrderRuleCreateRequest,
): Promise<OrderRule> {
  const { data } = await client.post<OrderRule>("/rules", req);
  return data;
}

export async function deleteRule(id: number): Promise<void> {
  await client.delete(`/rules/${id}`);
}

export async function updateRule(
  id: number,
  updates: Partial<OrderRuleCreateRequest & { is_active: boolean }>,
): Promise<OrderRule> {
  const { data } = await client.put<OrderRule>(`/rules/${id}`, updates);
  return data;
}

export async function evaluateRules(): Promise<RuleEvaluateResult[]> {
  const { data } = await client.post<RuleEvaluateResult[]>("/rules/evaluate");
  return data;
}

// Safety
export async function fetchSafetyStatus(): Promise<SafetyStatusResponse> {
  const { data } = await client.get<SafetyStatusResponse>("/risk/status");
  return data;
}

export async function updateSafetyConfig(
  updates: Partial<SafetyConfig>,
): Promise<SafetyConfig> {
  const { data } = await client.put<SafetyConfig>("/risk/config", updates);
  return data;
}

export async function activatePanic(): Promise<{ panic_mode: boolean; message: string }> {
  const { data } = await client.post<{ panic_mode: boolean; message: string }>(
    "/risk/panic",
  );
  return data;
}
