import { useCallback, useEffect, useState } from "react";
import {
  computeTaxLots,
  downloadTaxReport,
  fetchDailyEstimate,
  fetchTaxLots,
  fetchTaxSummary,
  fetchWashSales,
} from "../api/tax";
import LoadingSpinner from "../components/LoadingSpinner";
import type {
  DailyTaxEstimate,
  TaxLot,
  TaxSummary,
  WashSale,
} from "../types/tax";

function getCurrentFY(): string {
  const now = new Date();
  const year = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  return `${year}-${year + 1}`;
}

const FY_OPTIONS = ["2023-2024", "2024-2025", "2025-2026", "2026-2027"];

function fmt(n: number): string {
  return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export default function TaxReportPage() {
  const [fy, setFy] = useState(getCurrentFY());
  const [loading, setLoading] = useState(true);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [computeMsg, setComputeMsg] = useState<string | null>(null);

  const [summary, setSummary] = useState<TaxSummary | null>(null);
  const [lots, setLots] = useState<TaxLot[]>([]);
  const [washSales, setWashSales] = useState<WashSale[]>([]);
  const [dailyEstimates, setDailyEstimates] = useState<DailyTaxEstimate[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, l, w, d] = await Promise.all([
        fetchTaxSummary(fy),
        fetchTaxLots({ fy }),
        fetchWashSales(fy),
        fetchDailyEstimate(fy),
      ]);
      setSummary(s);
      setLots(l);
      setWashSales(w);
      setDailyEstimates(d);
    } catch {
      setError("Failed to load tax data.");
    } finally {
      setLoading(false);
    }
  }, [fy]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleCompute() {
    setComputing(true);
    setComputeMsg(null);
    try {
      const result = await computeTaxLots(fy);
      setComputeMsg(result.message);
      await loadData();
    } catch {
      setComputeMsg("Failed to compute tax lots.");
    } finally {
      setComputing(false);
    }
  }

  const latestEstimate = dailyEstimates.length > 0 ? dailyEstimates[dailyEstimates.length - 1] : null;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Tax Report</h1>
        <div className="flex items-center gap-3">
          <select
            value={fy}
            onChange={(e) => setFy(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {FY_OPTIONS.map((f) => (
              <option key={f} value={f}>
                FY {f}
              </option>
            ))}
          </select>
          <button
            onClick={handleCompute}
            disabled={computing}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {computing ? "Computing..." : "Compute Tax Lots"}
          </button>
          <button
            onClick={() => downloadTaxReport(fy)}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Download CSV
          </button>
        </div>
      </div>

      {computeMsg && (
        <div className="mb-4 rounded-lg border border-blue-300 bg-blue-50 p-3 text-sm text-blue-700">
          {computeMsg}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <LoadingSpinner />
      ) : (
        <>
          {/* Summary Cards */}
          {summary && (
            <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="text-xs font-medium uppercase text-gray-500">STCG</p>
                <p className={`text-xl font-bold ${summary.total_stcg >= 0 ? "text-green-700" : "text-red-700"}`}>
                  {fmt(summary.total_stcg)}
                </p>
                <p className="mt-1 text-xs text-gray-500">Tax: {fmt(summary.estimated_stcg_tax)}</p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="text-xs font-medium uppercase text-gray-500">LTCG</p>
                <p className={`text-xl font-bold ${summary.total_ltcg >= 0 ? "text-green-700" : "text-red-700"}`}>
                  {fmt(summary.total_ltcg)}
                </p>
                <p className="mt-1 text-xs text-gray-500">Tax: {fmt(summary.estimated_ltcg_tax)}</p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="text-xs font-medium uppercase text-gray-500">Intraday</p>
                <p className={`text-xl font-bold ${summary.total_intraday >= 0 ? "text-green-700" : "text-red-700"}`}>
                  {fmt(summary.total_intraday)}
                </p>
                <p className="mt-1 text-xs text-gray-500">Taxed at slab rate</p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="text-xs font-medium uppercase text-gray-500">F&O</p>
                <p className={`text-xl font-bold ${summary.total_fno >= 0 ? "text-green-700" : "text-red-700"}`}>
                  {fmt(summary.total_fno)}
                </p>
                <p className="mt-1 text-xs text-gray-500">Taxed at slab rate</p>
              </div>
            </div>
          )}

          {/* Advance Tax Reminder */}
          {latestEstimate && latestEstimate.advance_tax_due > 0 && (
            <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4">
              <p className="text-sm font-medium text-amber-800">
                Advance Tax Due: {fmt(latestEstimate.advance_tax_due)}
              </p>
              <p className="mt-1 text-xs text-amber-600">
                Estimated total tax liability: {fmt(latestEstimate.estimated_tax)} | As of{" "}
                {latestEstimate.date}
              </p>
            </div>
          )}

          {/* Wash Sale Warnings */}
          {washSales.length > 0 && (
            <div className="mb-6">
              <h2 className="mb-3 text-lg font-semibold text-gray-900">Wash Sale Advisories</h2>
              <div className="space-y-2">
                {washSales.map((ws, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg border border-orange-300 bg-orange-50 p-3"
                  >
                    <div>
                      <span className="font-medium text-orange-800">{ws.tradingsymbol}</span>
                      <span className="ml-2 text-sm text-orange-600">
                        Sold {new Date(ws.sell_date).toLocaleDateString()} @ {fmt(ws.sell_price)}, re-bought{" "}
                        {new Date(ws.rebuy_date).toLocaleDateString()} @ {fmt(ws.rebuy_price)}
                      </span>
                    </div>
                    <span className="text-sm font-medium text-red-700">Loss: {fmt(ws.loss_amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tax Lots Table */}
          <div className="mb-6">
            <h2 className="mb-3 text-lg font-semibold text-gray-900">Tax Lots</h2>
            {lots.length === 0 ? (
              <p className="text-sm text-gray-500">No tax lots found. Click "Compute Tax Lots" to generate.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium text-gray-500">Symbol</th>
                      <th className="px-4 py-2 text-left font-medium text-gray-500">Buy Date</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">Buy Price</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">Qty</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">Remaining</th>
                      <th className="px-4 py-2 text-left font-medium text-gray-500">Sell Date</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">Sell Price</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">P&L</th>
                      <th className="px-4 py-2 text-left font-medium text-gray-500">Type</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {lots.map((lot) => (
                      <tr key={lot.id}>
                        <td className="px-4 py-2 font-medium">{lot.tradingsymbol}</td>
                        <td className="px-4 py-2">{new Date(lot.buy_date).toLocaleDateString()}</td>
                        <td className="px-4 py-2 text-right">{fmt(lot.buy_price)}</td>
                        <td className="px-4 py-2 text-right">{lot.quantity}</td>
                        <td className="px-4 py-2 text-right">{lot.remaining_quantity}</td>
                        <td className="px-4 py-2">
                          {lot.sell_date ? new Date(lot.sell_date).toLocaleDateString() : "-"}
                        </td>
                        <td className="px-4 py-2 text-right">
                          {lot.sell_price != null ? fmt(lot.sell_price) : "-"}
                        </td>
                        <td
                          className={`px-4 py-2 text-right font-medium ${
                            lot.realized_pnl != null && lot.realized_pnl >= 0
                              ? "text-green-700"
                              : "text-red-700"
                          }`}
                        >
                          {lot.realized_pnl != null ? fmt(lot.realized_pnl) : "-"}
                        </td>
                        <td className="px-4 py-2">
                          <span
                            className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                              lot.holding_type === "LTCG"
                                ? "bg-green-100 text-green-700"
                                : lot.holding_type === "STCG"
                                  ? "bg-yellow-100 text-yellow-700"
                                  : lot.holding_type === "INTRADAY"
                                    ? "bg-blue-100 text-blue-700"
                                    : "bg-purple-100 text-purple-700"
                            }`}
                          >
                            {lot.holding_type}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Daily Tax Ticker */}
          {dailyEstimates.length > 0 && (
            <div>
              <h2 className="mb-3 text-lg font-semibold text-gray-900">Daily Tax Liability</h2>
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium text-gray-500">Date</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">STCG</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">LTCG</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">Intraday</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">F&O</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">Est. Tax</th>
                      <th className="px-4 py-2 text-right font-medium text-gray-500">Adv. Tax Due</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {dailyEstimates.map((d) => (
                      <tr key={d.date}>
                        <td className="px-4 py-2">{d.date}</td>
                        <td className="px-4 py-2 text-right">{fmt(d.stcg_to_date)}</td>
                        <td className="px-4 py-2 text-right">{fmt(d.ltcg_to_date)}</td>
                        <td className="px-4 py-2 text-right">{fmt(d.intraday_to_date)}</td>
                        <td className="px-4 py-2 text-right">{fmt(d.fno_to_date)}</td>
                        <td className="px-4 py-2 text-right font-medium">{fmt(d.estimated_tax)}</td>
                        <td className="px-4 py-2 text-right font-medium text-amber-700">
                          {fmt(d.advance_tax_due)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
