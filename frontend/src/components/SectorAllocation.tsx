import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { AllocationResponse } from "../types/portfolio";

const COLORS = [
  "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
  "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
];

interface Props {
  allocation: AllocationResponse;
}

export default function SectorAllocation({ allocation }: Props) {
  const data = allocation.allocations.map((a) => ({
    name: a.sector,
    value: a.weight,
    amount: a.value,
    count: a.holdings_count,
  }));

  if (data.length === 0) {
    return (
      <div className="rounded-lg bg-white p-5 shadow">
        <h3 className="mb-4 text-sm font-medium text-gray-500">Sector Allocation</h3>
        <p className="text-center text-gray-400">No allocation data</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <h3 className="mb-4 text-sm font-medium text-gray-500">Sector Allocation</h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            dataKey="value"
            nameKey="name"
            label={({ name, value }) => `${name} ${value.toFixed(1)}%`}
            labelLine={false}
          >
            {data.map((_, index) => (
              <Cell key={index} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number, _name: string, props: { payload?: { amount: number; count: number } }) => [
              `${value.toFixed(1)}% (${props.payload?.count ?? 0} stocks)`,
              props.payload?.amount.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }) ?? "",
            ]}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
