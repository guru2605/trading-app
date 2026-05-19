import type { PortfolioSummary } from "../types/portfolio";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function PnlText({ value, pct }: { value: number; pct: number }) {
  const color =
    value > 0 ? "text-green-600" : value < 0 ? "text-red-600" : "text-gray-600";
  const sign = value > 0 ? "+" : "";
  return (
    <span className={color}>
      {sign}
      {formatCurrency(value)} ({sign}
      {pct.toFixed(2)}%)
    </span>
  );
}

interface Props {
  summary: PortfolioSummary;
}

export default function SummaryCards({ summary }: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-lg bg-white p-5 shadow">
        <p className="text-sm text-gray-500">Total Value</p>
        <p className="mt-1 text-2xl font-semibold">
          {formatCurrency(summary.total_current)}
        </p>
        <p className="mt-1 text-xs text-gray-400">
          Invested: {formatCurrency(summary.total_invested)}
        </p>
      </div>

      <div className="rounded-lg bg-white p-5 shadow">
        <p className="text-sm text-gray-500">Overall P&L</p>
        <p className="mt-1 text-2xl font-semibold">
          <PnlText value={summary.total_pnl} pct={summary.total_pnl_pct} />
        </p>
      </div>

      <div className="rounded-lg bg-white p-5 shadow">
        <p className="text-sm text-gray-500">Day P&L</p>
        <p className="mt-1 text-2xl font-semibold">
          <PnlText value={summary.day_pnl} pct={summary.day_pnl_pct} />
        </p>
      </div>

      <div className="rounded-lg bg-white p-5 shadow">
        <p className="text-sm text-gray-500">Holdings</p>
        <p className="mt-1 text-2xl font-semibold">{summary.holdings_count}</p>
        <p className="mt-1 text-xs text-gray-400">Active positions</p>
      </div>
    </div>
  );
}
