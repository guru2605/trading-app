import { useCallback, useEffect, useState } from "react";
import {
  checkAlerts,
  createAlert,
  deleteAlert,
  fetchAlerts,
  updateAlert,
} from "../api/alerts";
import LoadingSpinner from "../components/LoadingSpinner";
import type { Alert, AlertCheckResponse } from "../types/trade";

export default function AlertsPage() {
  const [loading, setLoading] = useState(true);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<AlertCheckResponse | null>(null);
  const [checking, setChecking] = useState(false);

  // New alert form
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [alertType, setAlertType] = useState("price_above");
  const [targetValue, setTargetValue] = useState("");
  const [creating, setCreating] = useState(false);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAlerts();
      setAlerts(data);
    } catch {
      setError("Failed to load alerts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  async function handleCreate() {
    if (!symbol || !targetValue) return;
    setCreating(true);
    try {
      await createAlert({
        tradingsymbol: symbol.toUpperCase(),
        exchange,
        alert_type: alertType,
        target_value: parseFloat(targetValue),
      });
      setSymbol("");
      setTargetValue("");
      await loadAlerts();
    } catch {
      setError("Failed to create alert.");
    } finally {
      setCreating(false);
    }
  }

  async function handleToggle(alert: Alert) {
    try {
      await updateAlert(alert.id, { is_active: !alert.is_active });
      await loadAlerts();
    } catch {
      setError("Failed to update alert.");
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteAlert(id);
      await loadAlerts();
    } catch {
      setError("Failed to delete alert.");
    }
  }

  async function handleCheck() {
    setChecking(true);
    setCheckResult(null);
    try {
      const result = await checkAlerts();
      setCheckResult(result);
      await loadAlerts();
    } catch {
      setError("Failed to check alerts. Check Kite connection.");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Price Alerts</h1>
        <button
          onClick={handleCheck}
          disabled={checking}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {checking ? "Checking..." : "Check Alerts"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {checkResult && (
        <div className="mb-4 rounded-lg border border-blue-300 bg-blue-50 p-4 text-sm text-blue-700">
          Checked {checkResult.checked} alerts, {checkResult.triggered} triggered.
          {checkResult.results
            .filter((r) => r.triggered)
            .map((r) => (
              <div key={r.tradingsymbol} className="mt-1">
                {r.tradingsymbol}: {r.alert_type} target {r.target_value}, current{" "}
                {r.current_price}
              </div>
            ))}
        </div>
      )}

      {/* Create alert form */}
      <div className="mb-6 rounded-lg bg-white p-4 shadow">
        <h2 className="mb-3 text-lg font-semibold text-gray-800">New Alert</h2>
        <div className="flex flex-wrap gap-3">
          <input
            type="text"
            placeholder="Symbol (e.g. RELIANCE)"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <select
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
          </select>
          <select
            value={alertType}
            onChange={(e) => setAlertType(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="price_above">Price Above</option>
            <option value="price_below">Price Below</option>
            <option value="pct_change">% Change</option>
          </select>
          <input
            type="number"
            placeholder="Target value"
            value={targetValue}
            onChange={(e) => setTargetValue(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !symbol || !targetValue}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {creating ? "Creating..." : "Create"}
          </button>
        </div>
      </div>

      {/* Alerts table */}
      {loading ? (
        <LoadingSpinner />
      ) : (
        <div className="overflow-x-auto rounded-lg bg-white shadow">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              <tr>
                <th className="px-4 py-3">Symbol</th>
                <th className="px-4 py-3">Exchange</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3 text-right">Target</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Triggered</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {alerts.map((a) => (
                <tr key={a.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{a.tradingsymbol}</td>
                  <td className="px-4 py-3">{a.exchange}</td>
                  <td className="px-4 py-3">{a.alert_type.replace("_", " ")}</td>
                  <td className="px-4 py-3 text-right">{a.target_value}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${
                        a.is_active
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {a.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {a.triggered_at
                      ? new Date(a.triggered_at).toLocaleString("en-IN")
                      : "-"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleToggle(a)}
                        className="text-sm text-blue-600 hover:underline"
                      >
                        {a.is_active ? "Pause" : "Resume"}
                      </button>
                      <button
                        onClick={() => handleDelete(a.id)}
                        className="text-sm text-red-600 hover:underline"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {alerts.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                    No alerts yet. Create one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
