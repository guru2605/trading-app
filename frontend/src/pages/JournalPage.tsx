import { useCallback, useEffect, useState } from "react";
import {
  acknowledgeBehaviorFlag,
  createJournalEntry,
  deleteJournalEntry,
  fetchAnalytics,
  fetchBehaviorFlags,
  fetchJournalEntries,
  runBehaviorDetection,
  updateJournalEntry,
} from "../api/journal";
import LoadingSpinner from "../components/LoadingSpinner";
import type {
  BehaviorFlag,
  JournalAnalytics,
  JournalEntry,
} from "../types/journal";

const ENTRY_TYPES = ["post_trade", "pre_trade", "note"];
const OUTCOMES = ["", "win", "loss", "breakeven"];
const STRATEGIES = ["", "breakout", "mean_reversion", "scalp", "momentum", "swing"];
const EMOTIONAL_STATES = ["", "confident", "anxious", "fomo", "revenge", "neutral"];

const SEVERITY_COLORS: Record<string, string> = {
  info: "bg-blue-100 text-blue-700",
  warning: "bg-amber-100 text-amber-700",
  critical: "bg-red-100 text-red-700",
};

export default function JournalPage() {
  const [loading, setLoading] = useState(true);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [analytics, setAnalytics] = useState<JournalAnalytics | null>(null);
  const [behaviorFlags, setBehaviorFlags] = useState<BehaviorFlag[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [filterSymbol, setFilterSymbol] = useState("");
  const [filterType, setFilterType] = useState("");

  // Create form
  const [symbol, setSymbol] = useState("");
  const [entryType, setEntryType] = useState("post_trade");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [strategy, setStrategy] = useState("");
  const [outcome, setOutcome] = useState("");
  const [emotionalState, setEmotionalState] = useState("");
  const [creating, setCreating] = useState(false);

  // Edit
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editOutcome, setEditOutcome] = useState("");

  // Behavior detection
  const [detecting, setDetecting] = useState(false);
  const [detectionMessage, setDetectionMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (filterSymbol) params.tradingsymbol = filterSymbol;
      if (filterType) params.entry_type = filterType;

      const [entryData, analyticsData, flagsData] = await Promise.all([
        fetchJournalEntries(params),
        fetchAnalytics(),
        fetchBehaviorFlags({ is_acknowledged: false }),
      ]);
      setEntries(entryData);
      setAnalytics(analyticsData);
      setBehaviorFlags(flagsData);
    } catch {
      setError("Failed to load journal data.");
    } finally {
      setLoading(false);
    }
  }, [filterSymbol, filterType]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleCreate() {
    if (!symbol) return;
    setCreating(true);
    try {
      await createJournalEntry({
        tradingsymbol: symbol.toUpperCase(),
        entry_type: entryType,
        content,
        tags,
        strategy,
        outcome,
        emotional_state: emotionalState,
      });
      setSymbol("");
      setContent("");
      setTags("");
      setStrategy("");
      setOutcome("");
      setEmotionalState("");
      await loadData();
    } catch {
      setError("Failed to create journal entry.");
    } finally {
      setCreating(false);
    }
  }

  async function handleUpdate(id: number) {
    try {
      await updateJournalEntry(id, {
        content: editContent,
        outcome: editOutcome,
      });
      setEditingId(null);
      await loadData();
    } catch {
      setError("Failed to update entry.");
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteJournalEntry(id);
      await loadData();
    } catch {
      setError("Failed to delete entry.");
    }
  }

  async function handleDetect() {
    setDetecting(true);
    setDetectionMessage(null);
    try {
      const result = await runBehaviorDetection();
      setDetectionMessage(result.summary);
      await loadData();
    } catch {
      setError("Failed to run behavior detection.");
    } finally {
      setDetecting(false);
    }
  }

  async function handleAcknowledge(flagId: number) {
    try {
      await acknowledgeBehaviorFlag(flagId, true);
      await loadData();
    } catch {
      setError("Failed to acknowledge flag.");
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Trade Journal</h1>
        <button
          onClick={handleDetect}
          disabled={detecting}
          className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
        >
          {detecting ? "Detecting..." : "Run Behavior Detection"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {detectionMessage && (
        <div className="mb-4 rounded-lg border border-purple-300 bg-purple-50 p-4 text-sm text-purple-700">
          {detectionMessage}
        </div>
      )}

      {/* Behavior flags */}
      {behaviorFlags.length > 0 && (
        <div className="mb-6 rounded-lg bg-white p-4 shadow">
          <h2 className="mb-3 text-lg font-semibold text-gray-800">
            Behavioral Alerts ({behaviorFlags.length})
          </h2>
          <div className="space-y-2">
            {behaviorFlags.map((flag) => (
              <div
                key={flag.id}
                className="flex items-center justify-between rounded-lg border border-gray-200 p-3"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${
                      SEVERITY_COLORS[flag.severity] || "bg-gray-100 text-gray-700"
                    }`}
                  >
                    {flag.severity}
                  </span>
                  <span className="text-xs font-medium text-gray-500">
                    {flag.flag_type.replace("_", " ")}
                  </span>
                  <span className="text-sm text-gray-700">
                    {flag.description}
                  </span>
                </div>
                <button
                  onClick={() => handleAcknowledge(flag.id)}
                  className="text-sm text-blue-600 hover:underline"
                >
                  Acknowledge
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analytics cards */}
      {analytics && analytics.total_entries > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-lg bg-white p-4 shadow">
            <p className="text-sm text-gray-500">Total Entries</p>
            <p className="text-2xl font-bold text-gray-900">
              {analytics.total_entries}
            </p>
          </div>
          <div className="rounded-lg bg-white p-4 shadow">
            <p className="text-sm text-gray-500">Win Rate</p>
            <p className="text-2xl font-bold text-green-600">
              {analytics.win_rate.toFixed(1)}%
            </p>
          </div>
          <div className="rounded-lg bg-white p-4 shadow">
            <p className="text-sm text-gray-500">Wins / Losses</p>
            <p className="text-2xl font-bold text-gray-900">
              <span className="text-green-600">{analytics.total_wins}</span>
              {" / "}
              <span className="text-red-600">{analytics.total_losses}</span>
            </p>
          </div>
          <div className="rounded-lg bg-white p-4 shadow">
            <p className="text-sm text-gray-500">Strategies</p>
            <p className="text-2xl font-bold text-gray-900">
              {analytics.by_strategy.length}
            </p>
          </div>
        </div>
      )}

      {/* Strategy breakdown */}
      {analytics && analytics.by_strategy.length > 0 && (
        <div className="mb-6 rounded-lg bg-white p-4 shadow">
          <h2 className="mb-3 text-lg font-semibold text-gray-800">
            Performance by Strategy
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                <tr>
                  <th className="px-4 py-2">Strategy</th>
                  <th className="px-4 py-2 text-right">Trades</th>
                  <th className="px-4 py-2 text-right">Wins</th>
                  <th className="px-4 py-2 text-right">Losses</th>
                  <th className="px-4 py-2 text-right">Win Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {analytics.by_strategy.map((s) => (
                  <tr key={s.strategy}>
                    <td className="px-4 py-2 font-medium capitalize">
                      {s.strategy.replace("_", " ")}
                    </td>
                    <td className="px-4 py-2 text-right">{s.count}</td>
                    <td className="px-4 py-2 text-right text-green-600">
                      {s.wins}
                    </td>
                    <td className="px-4 py-2 text-right text-red-600">
                      {s.losses}
                    </td>
                    <td className="px-4 py-2 text-right font-medium">
                      {s.win_rate.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create form */}
      <div className="mb-6 rounded-lg bg-white p-4 shadow">
        <h2 className="mb-3 text-lg font-semibold text-gray-800">
          New Journal Entry
        </h2>
        <div className="mb-3 flex flex-wrap gap-3">
          <input
            type="text"
            placeholder="Symbol (e.g. RELIANCE)"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <select
            value={entryType}
            onChange={(e) => setEntryType(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {ENTRY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace("_", " ")}
              </option>
            ))}
          </select>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {STRATEGIES.map((s) => (
              <option key={s} value={s}>
                {s ? s.replace("_", " ") : "Strategy..."}
              </option>
            ))}
          </select>
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>
                {o || "Outcome..."}
              </option>
            ))}
          </select>
          <select
            value={emotionalState}
            onChange={(e) => setEmotionalState(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {EMOTIONAL_STATES.map((e) => (
              <option key={e} value={e}>
                {e || "Emotional state..."}
              </option>
            ))}
          </select>
        </div>
        <div className="mb-3">
          <textarea
            placeholder="Notes / analysis..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            placeholder="Tags (comma-separated)"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !symbol}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {creating ? "Creating..." : "Create"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex gap-3">
        <input
          type="text"
          placeholder="Filter by symbol..."
          value={filterSymbol}
          onChange={(e) => setFilterSymbol(e.target.value.toUpperCase())}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All types</option>
          {ENTRY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      {/* Entries list */}
      {loading ? (
        <LoadingSpinner />
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="rounded-lg bg-white p-4 shadow"
            >
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-gray-900">
                    {entry.tradingsymbol}
                  </span>
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                    {entry.entry_type.replace("_", " ")}
                  </span>
                  {entry.strategy && (
                    <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                      {entry.strategy}
                    </span>
                  )}
                  {entry.outcome && (
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-semibold ${
                        entry.outcome === "win"
                          ? "bg-green-100 text-green-700"
                          : entry.outcome === "loss"
                            ? "bg-red-100 text-red-700"
                            : "bg-gray-100 text-gray-700"
                      }`}
                    >
                      {entry.outcome}
                    </span>
                  )}
                  {entry.emotional_state && (
                    <span className="rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-700">
                      {entry.emotional_state}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">
                    {new Date(entry.created_at).toLocaleString("en-IN")}
                  </span>
                  <button
                    onClick={() => {
                      setEditingId(entry.id);
                      setEditContent(entry.content);
                      setEditOutcome(entry.outcome);
                    }}
                    className="text-sm text-blue-600 hover:underline"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(entry.id)}
                    className="text-sm text-red-600 hover:underline"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {editingId === entry.id ? (
                <div className="mt-2 space-y-2">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={3}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  />
                  <div className="flex items-center gap-2">
                    <select
                      value={editOutcome}
                      onChange={(e) => setEditOutcome(e.target.value)}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
                    >
                      {OUTCOMES.map((o) => (
                        <option key={o} value={o}>
                          {o || "No outcome"}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleUpdate(entry.id)}
                      className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="text-sm text-gray-500 hover:underline"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                entry.content && (
                  <p className="text-sm text-gray-700">{entry.content}</p>
                )
              )}

              {entry.tags && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {entry.tags.split(",").map((tag) => (
                    <span
                      key={tag.trim()}
                      className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
                    >
                      {tag.trim()}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}

          {entries.length === 0 && (
            <div className="rounded-lg bg-white p-8 text-center text-gray-400 shadow">
              No journal entries yet. Create one above.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
