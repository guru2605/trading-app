import { useCallback, useEffect, useRef, useState } from "react";
import {
  addToWatchlist,
  fetchSignals,
  fetchWatchlist,
  importFromHoldings,
  removeFromWatchlist,
  runScan,
  searchInstruments,
  updateSignalStatus,
} from "../api/scanner";
import LoadingSpinner from "../components/LoadingSpinner";
import type {
  InstrumentSearchResult,
  ScanResponse,
  Signal,
  WatchlistItem,
} from "../types/scanner";

export default function ScannerPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Watchlist
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [notes, setNotes] = useState("");
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const [searchResults, setSearchResults] = useState<InstrumentSearchResult[]>(
    [],
  );
  const [showSearch, setShowSearch] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // Scanner
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [timeframe, setTimeframe] = useState("15minute");

  // Signals
  const [signals, setSignals] = useState<Signal[]>([]);
  const [statusFilter, setStatusFilter] = useState("active");
  const [expandedSignal, setExpandedSignal] = useState<number | null>(null);

  const loadWatchlist = useCallback(async () => {
    try {
      const data = await fetchWatchlist();
      setWatchlist(data);
    } catch {
      setError("Failed to load watchlist.");
    }
  }, []);

  const loadSignals = useCallback(async () => {
    try {
      const data = await fetchSignals(
        statusFilter ? { status: statusFilter } : undefined,
      );
      setSignals(data);
    } catch {
      setError("Failed to load signals.");
    }
  }, [statusFilter]);

  useEffect(() => {
    async function init() {
      setLoading(true);
      await Promise.all([loadWatchlist(), loadSignals()]);
      setLoading(false);
    }
    init();
  }, [loadWatchlist, loadSignals]);

  // Close search dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowSearch(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function handleSymbolSearch(value: string) {
    setSymbol(value);
    if (value.length >= 2) {
      try {
        const results = await searchInstruments(value, exchange);
        setSearchResults(results);
        setShowSearch(true);
      } catch {
        setSearchResults([]);
      }
    } else {
      setSearchResults([]);
      setShowSearch(false);
    }
  }

  function handleSelectInstrument(inst: InstrumentSearchResult) {
    setSymbol(inst.tradingsymbol);
    setShowSearch(false);
  }

  async function handleAddSymbol() {
    if (!symbol) return;
    setAdding(true);
    setError(null);
    try {
      await addToWatchlist({
        tradingsymbol: symbol.toUpperCase(),
        exchange,
        notes,
      });
      setSymbol("");
      setNotes("");
      await loadWatchlist();
    } catch {
      setError("Failed to add symbol.");
    } finally {
      setAdding(false);
    }
  }

  async function handleImportHoldings() {
    setImporting(true);
    setError(null);
    try {
      const result = await importFromHoldings();
      if (result.added > 0) {
        await loadWatchlist();
      }
      setError(
        result.added > 0
          ? null
          : "No new symbols to import — all holdings already in watchlist.",
      );
    } catch {
      setError("Failed to import from holdings. Sync holdings first.");
    } finally {
      setImporting(false);
    }
  }

  async function handleRemove(id: number) {
    try {
      await removeFromWatchlist(id);
      await loadWatchlist();
    } catch {
      setError("Failed to remove symbol.");
    }
  }

  async function handleScan() {
    setScanning(true);
    setScanResult(null);
    setError(null);
    try {
      const result = await runScan({ timeframe });
      setScanResult(result);
      await loadSignals();
    } catch {
      setError("Failed to run scan. Check Kite connection.");
    } finally {
      setScanning(false);
    }
  }

  async function handleUpdateStatus(id: number, status: string) {
    try {
      await updateSignalStatus(id, { status });
      await loadSignals();
    } catch {
      setError("Failed to update signal.");
    }
  }

  function confidenceColor(c: number): string {
    if (c >= 70) return "bg-green-500";
    if (c >= 50) return "bg-yellow-500";
    return "bg-red-400";
  }

  if (loading) return <LoadingSpinner />;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Watchlist Section */}
      <div className="mb-6 rounded-lg bg-white p-4 shadow">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800">Watchlist</h2>
          <button
            onClick={handleImportHoldings}
            disabled={importing}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {importing ? "Importing..." : "Import from Holdings"}
          </button>
        </div>
        <div className="mb-4 flex flex-wrap gap-3">
          <div className="relative" ref={searchRef}>
            <input
              type="text"
              placeholder="Search symbol (e.g. REL)"
              value={symbol}
              onChange={(e) => handleSymbolSearch(e.target.value.toUpperCase())}
              onFocus={() => searchResults.length > 0 && setShowSearch(true)}
              className="w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            {showSearch && searchResults.length > 0 && (
              <div className="absolute z-10 mt-1 max-h-48 w-72 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
                {searchResults.map((r) => (
                  <button
                    key={r.tradingsymbol}
                    onClick={() => handleSelectInstrument(r)}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-blue-50"
                  >
                    <span className="font-medium">{r.tradingsymbol}</span>
                    <span className="truncate pl-2 text-xs text-gray-400">
                      {r.name}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <select
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
          </select>
          <input
            type="text"
            placeholder="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={handleAddSymbol}
            disabled={adding || !symbol}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {adding ? "Adding..." : "Add"}
          </button>
        </div>
        {watchlist.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {watchlist.map((w) => (
              <span
                key={w.id}
                className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-3 py-1 text-sm text-blue-800"
              >
                {w.tradingsymbol}
                <span className="text-xs text-blue-500">{w.exchange}</span>
                <button
                  onClick={() => handleRemove(w.id)}
                  className="ml-1 text-blue-400 hover:text-red-600"
                >
                  x
                </button>
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400">
            No symbols in watchlist. Add symbols above.
          </p>
        )}
      </div>

      {/* Scanner Controls */}
      <div className="mb-6 flex items-center gap-4">
        <h1 className="text-2xl font-bold text-gray-900">Scanner</h1>
        <select
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="5minute">5 min</option>
          <option value="15minute">15 min</option>
          <option value="30minute">30 min</option>
          <option value="day">Daily</option>
        </select>
        <button
          onClick={handleScan}
          disabled={scanning || watchlist.length === 0}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {scanning ? "Scanning..." : "Run Scan"}
        </button>
      </div>

      {scanResult && (
        <div className="mb-4 space-y-2">
          <div className="rounded-lg border border-blue-300 bg-blue-50 p-4 text-sm text-blue-700">
            Scanned {scanResult.scanned} symbols, generated{" "}
            {scanResult.signals_generated} signal(s).
          </div>
          {scanResult.errors.length > 0 && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-700">
              <p className="mb-1 font-medium">
                {scanResult.errors.length} issue(s) during scan:
              </p>
              <ul className="list-inside list-disc space-y-0.5">
                {scanResult.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Signals */}
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-lg font-semibold text-gray-800">Signals</h2>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="active">Active</option>
          <option value="executed">Executed</option>
          <option value="expired">Expired</option>
          <option value="">All</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-lg bg-white shadow">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
            <tr>
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Timeframe</th>
              <th className="px-4 py-3 text-right">Entry</th>
              <th className="px-4 py-3 text-right">SL</th>
              <th className="px-4 py-3 text-right">Target</th>
              <th className="px-4 py-3">Confidence</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {signals.map((s) => (
              <>
                <tr
                  key={s.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() =>
                    setExpandedSignal(expandedSignal === s.id ? null : s.id)
                  }
                >
                  <td className="px-4 py-3 font-medium">{s.tradingsymbol}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${
                        s.signal_type === "BUY"
                          ? "bg-green-100 text-green-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {s.signal_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{s.timeframe}</td>
                  <td className="px-4 py-3 text-right">{s.entry_price}</td>
                  <td className="px-4 py-3 text-right text-red-600">
                    {s.stop_loss}
                  </td>
                  <td className="px-4 py-3 text-right text-green-600">
                    {s.target_price}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-16 rounded-full bg-gray-200">
                        <div
                          className={`h-2 rounded-full ${confidenceColor(s.confidence)}`}
                          style={{ width: `${s.confidence}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-600">
                        {s.confidence}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${
                        s.status === "active"
                          ? "bg-blue-100 text-blue-700"
                          : s.status === "executed"
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {s.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {s.status === "active" && (
                      <div className="flex gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleUpdateStatus(s.id, "executed");
                          }}
                          className="text-sm text-green-600 hover:underline"
                        >
                          Executed
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleUpdateStatus(s.id, "expired");
                          }}
                          className="text-sm text-gray-500 hover:underline"
                        >
                          Expire
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
                {expandedSignal === s.id && (
                  <tr key={`${s.id}-detail`}>
                    <td colSpan={9} className="bg-gray-50 px-6 py-4">
                      <div className="space-y-2 text-sm">
                        <p className="font-medium text-gray-700">Rationale</p>
                        <p className="text-gray-600">{s.rationale}</p>
                        <p className="font-medium text-gray-700">
                          Created:{" "}
                          <span className="font-normal">
                            {new Date(s.created_at).toLocaleString("en-IN")}
                          </span>
                        </p>
                        {s.expired_at && (
                          <p className="font-medium text-gray-700">
                            Expired:{" "}
                            <span className="font-normal">
                              {new Date(s.expired_at).toLocaleString("en-IN")}
                            </span>
                          </p>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
            {signals.length === 0 && (
              <tr>
                <td
                  colSpan={9}
                  className="px-4 py-8 text-center text-gray-400"
                >
                  No signals found. Add symbols to watchlist and run a scan.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
