import type { ExposureResponse } from "../types/portfolio";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function getLeverageColor(leverage: number): string {
  if (leverage <= 1.0) return "bg-green-500";
  if (leverage <= 1.5) return "bg-yellow-500";
  return "bg-red-500";
}

function getLeverageLabel(leverage: number): string {
  if (leverage <= 1.0) return "Safe";
  if (leverage <= 1.5) return "Moderate";
  return "High";
}

interface Props {
  exposure: ExposureResponse;
}

export default function ExposureMeter({ exposure }: Props) {
  const leveragePct = Math.min(exposure.leverage * 50, 100);
  const color = getLeverageColor(exposure.leverage);

  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <h3 className="mb-4 text-sm font-medium text-gray-500">Exposure & Leverage</h3>

      <div className="mb-4">
        <div className="mb-1 flex items-center justify-between text-sm">
          <span>Leverage: {exposure.leverage.toFixed(2)}x</span>
          <span className={`rounded px-2 py-0.5 text-xs font-medium text-white ${color}`}>
            {getLeverageLabel(exposure.leverage)}
          </span>
        </div>
        <div className="h-3 w-full overflow-hidden rounded-full bg-gray-200">
          <div className={`h-full rounded-full ${color}`} style={{ width: `${leveragePct}%` }} />
        </div>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Total Exposure</span>
          <span className="font-medium">{formatCurrency(exposure.total_exposure)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Long</span>
          <span className="font-medium text-green-600">{formatCurrency(exposure.long_exposure)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Short</span>
          <span className="font-medium text-red-600">{formatCurrency(exposure.short_exposure)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Net Exposure</span>
          <span className="font-medium">{formatCurrency(exposure.net_exposure)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Directional Bias</span>
          <span className="font-medium capitalize">{exposure.directional_bias}</span>
        </div>
      </div>
    </div>
  );
}
