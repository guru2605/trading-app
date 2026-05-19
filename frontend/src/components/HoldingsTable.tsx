import { useState } from "react";
import type { Holding } from "../types/portfolio";

type SortKey = "tradingsymbol" | "quantity" | "last_price" | "pnl" | "weight" | "day_change_pct";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

interface Props {
  holdings: Holding[];
}

export default function HoldingsTable({ holdings }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("weight");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...holdings].sort((a, b) => {
    const aVal = a[sortKey];
    const bVal = b[sortKey];
    if (typeof aVal === "string" && typeof bVal === "string") {
      return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }
    return sortAsc
      ? (aVal as number) - (bVal as number)
      : (bVal as number) - (aVal as number);
  });

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortAsc ? " \u25B2" : " \u25BC") : "";

  return (
    <div className="overflow-x-auto rounded-lg bg-white shadow">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
          <tr>
            <th className="cursor-pointer px-4 py-3" onClick={() => handleSort("tradingsymbol")}>
              Symbol{arrow("tradingsymbol")}
            </th>
            <th className="cursor-pointer px-4 py-3 text-right" onClick={() => handleSort("quantity")}>
              Qty{arrow("quantity")}
            </th>
            <th className="px-4 py-3 text-right">Avg Price</th>
            <th className="cursor-pointer px-4 py-3 text-right" onClick={() => handleSort("last_price")}>
              LTP{arrow("last_price")}
            </th>
            <th className="cursor-pointer px-4 py-3 text-right" onClick={() => handleSort("pnl")}>
              P&L{arrow("pnl")}
            </th>
            <th className="cursor-pointer px-4 py-3 text-right" onClick={() => handleSort("day_change_pct")}>
              Day %{arrow("day_change_pct")}
            </th>
            <th className="cursor-pointer px-4 py-3 text-right" onClick={() => handleSort("weight")}>
              Weight{arrow("weight")}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((h) => (
            <tr key={h.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{h.tradingsymbol}</td>
              <td className="px-4 py-3 text-right">{h.quantity}</td>
              <td className="px-4 py-3 text-right">{formatCurrency(h.average_price)}</td>
              <td className="px-4 py-3 text-right">{formatCurrency(h.last_price)}</td>
              <td className={`px-4 py-3 text-right ${h.pnl >= 0 ? "text-green-600" : "text-red-600"}`}>
                {formatCurrency(h.pnl)}
              </td>
              <td className={`px-4 py-3 text-right ${h.day_change_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
                {h.day_change_pct.toFixed(2)}%
              </td>
              <td className="px-4 py-3 text-right">{h.weight.toFixed(1)}%</td>
            </tr>
          ))}
          {holdings.length === 0 && (
            <tr>
              <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                No holdings found. Sync from Kite to get started.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
