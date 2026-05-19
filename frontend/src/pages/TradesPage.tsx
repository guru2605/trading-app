import { useCallback, useEffect, useState } from "react";
import { fetchTrades, syncTrades } from "../api/trades";
import LoadingSpinner from "../components/LoadingSpinner";
import TradesTable from "../components/TradesTable";
import type { Trade } from "../types/trade";

export default function TradesPage() {
  const [loading, setLoading] = useState(true);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadTrades = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = {};
      if (symbolFilter) params.tradingsymbol = symbolFilter;
      if (typeFilter) params.transaction_type = typeFilter;
      const data = await fetchTrades(params);
      setTrades(data);
    } catch {
      setError("Failed to load trades.");
    } finally {
      setLoading(false);
    }
  }, [symbolFilter, typeFilter]);

  useEffect(() => {
    loadTrades();
  }, [loadTrades]);

  async function handleSync() {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await syncTrades();
      setSyncMessage(result.message);
      await loadTrades();
    } catch {
      setSyncMessage("Sync failed. Check Kite connection.");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Trade History</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={handleSync}
            disabled={syncing}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {syncing ? "Syncing..." : "Sync Trades"}
          </button>
          {syncMessage && <span className="text-sm text-gray-600">{syncMessage}</span>}
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="mb-4 flex gap-4">
        <input
          type="text"
          placeholder="Filter by symbol..."
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        >
          <option value="">All Types</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
      </div>

      {loading ? <LoadingSpinner /> : <TradesTable trades={trades} />}
    </div>
  );
}
