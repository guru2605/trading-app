import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RiskSnapshot } from "../types/trade";

interface Props {
  snapshots: RiskSnapshot[];
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export default function RiskChart({ snapshots }: Props) {
  if (snapshots.length === 0) {
    return (
      <div className="rounded-lg bg-white p-6 shadow">
        <h3 className="mb-2 text-lg font-semibold text-gray-800">P&L History</h3>
        <p className="text-sm text-gray-400">No snapshots yet. Create one to track P&L over time.</p>
      </div>
    );
  }

  // Show oldest first for the chart
  const data = [...snapshots].reverse().map((s) => ({
    date: s.snapshot_date,
    total_pnl: s.total_pnl,
    day_pnl: s.day_pnl,
    total_current: s.total_current,
  }));

  return (
    <div className="rounded-lg bg-white p-6 shadow">
      <h3 className="mb-4 text-lg font-semibold text-gray-800">P&L History</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 12 }} />
          <YAxis
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => formatCurrency(v)}
          />
          <Tooltip
            formatter={(value: number) => formatCurrency(value)}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="total_pnl"
            stroke="#2563eb"
            name="Total P&L"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
          <Line
            type="monotone"
            dataKey="day_pnl"
            stroke="#16a34a"
            name="Day P&L"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
