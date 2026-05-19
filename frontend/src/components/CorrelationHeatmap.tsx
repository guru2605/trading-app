import type { CorrelationResponse } from "../types/portfolio";

function getColor(value: number): string {
  if (value >= 0.8) return "bg-red-500 text-white";
  if (value >= 0.6) return "bg-red-300 text-white";
  if (value >= 0.3) return "bg-orange-200";
  if (value >= -0.3) return "bg-gray-100";
  if (value >= -0.6) return "bg-blue-200";
  return "bg-blue-400 text-white";
}

interface Props {
  correlation: CorrelationResponse;
}

export default function CorrelationHeatmap({ correlation }: Props) {
  const { symbols, matrix } = correlation;

  if (symbols.length < 2) {
    return (
      <div className="rounded-lg bg-white p-5 shadow">
        <h3 className="mb-4 text-sm font-medium text-gray-500">Correlation Matrix</h3>
        <p className="text-center text-gray-400">Need at least 2 holdings for correlation analysis</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <h3 className="mb-4 text-sm font-medium text-gray-500">Correlation Matrix (90d)</h3>
      <div className="overflow-x-auto">
        <table className="text-xs">
          <thead>
            <tr>
              <th className="px-2 py-1" />
              {symbols.map((s) => (
                <th key={s} className="px-2 py-1 text-center font-medium">
                  {s.length > 8 ? s.slice(0, 8) + "…" : s}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {symbols.map((rowSymbol, i) => (
              <tr key={rowSymbol}>
                <td className="px-2 py-1 font-medium">{rowSymbol}</td>
                {matrix[i].map((val, j) => (
                  <td
                    key={j}
                    className={`px-2 py-1 text-center ${i === j ? "bg-gray-300 font-bold" : getColor(val)}`}
                  >
                    {val.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {correlation.high_correlations.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-gray-500">Highly Correlated Pairs:</p>
          <ul className="mt-1 space-y-1">
            {correlation.high_correlations.map((pair, i) => (
              <li key={i} className="text-xs">
                <span className="font-medium">{pair.stock_a}</span>
                {" — "}
                <span className="font-medium">{pair.stock_b}</span>
                {": "}
                <span className={pair.correlation >= 0.8 ? "font-bold text-red-600" : "text-orange-600"}>
                  {pair.correlation.toFixed(4)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
