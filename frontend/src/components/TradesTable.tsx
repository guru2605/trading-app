import { useState } from "react";
import type { Trade } from "../types/trade";

type SortKey = "tradingsymbol" | "transaction_type" | "quantity" | "price" | "created_at";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

interface Props {
  trades: Trade[];
}

export default function TradesTable({ trades }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...trades].sort((a, b) => {
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
            <th className="cursor-pointer px-4 py-3" onClick={() => handleSort("transaction_type")}>
              Type{arrow("transaction_type")}
            </th>
            <th className="cursor-pointer px-4 py-3 text-right" onClick={() => handleSort("quantity")}>
              Qty{arrow("quantity")}
            </th>
            <th className="cursor-pointer px-4 py-3 text-right" onClick={() => handleSort("price")}>
              Price{arrow("price")}
            </th>
            <th className="px-4 py-3">Product</th>
            <th className="px-4 py-3">Order Type</th>
            <th className="px-4 py-3">Status</th>
            <th className="cursor-pointer px-4 py-3" onClick={() => handleSort("created_at")}>
              Date{arrow("created_at")}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((t) => (
            <tr key={t.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{t.tradingsymbol}</td>
              <td className="px-4 py-3">
                <span
                  className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${
                    t.transaction_type === "BUY"
                      ? "bg-green-100 text-green-700"
                      : "bg-red-100 text-red-700"
                  }`}
                >
                  {t.transaction_type}
                </span>
              </td>
              <td className="px-4 py-3 text-right">{t.quantity}</td>
              <td className="px-4 py-3 text-right">{formatCurrency(t.price)}</td>
              <td className="px-4 py-3">{t.product}</td>
              <td className="px-4 py-3">{t.order_type}</td>
              <td className="px-4 py-3">{t.status}</td>
              <td className="px-4 py-3 text-gray-500">
                {new Date(t.created_at).toLocaleDateString("en-IN")}
              </td>
            </tr>
          ))}
          {trades.length === 0 && (
            <tr>
              <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                No trades found. Sync from Kite to get started.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
