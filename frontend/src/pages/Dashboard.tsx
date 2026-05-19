import { useCallback, useEffect, useState } from "react";
import {
  fetchAllocation,
  fetchCorrelation,
  fetchExposure,
  fetchHoldings,
  fetchSummary,
} from "../api/portfolio";
import { fetchSnapshots } from "../api/trades";
import ConcentrationBanner from "../components/ConcentrationBanner";
import CorrelationHeatmap from "../components/CorrelationHeatmap";
import ExposureMeter from "../components/ExposureMeter";
import HoldingsTable from "../components/HoldingsTable";
import LoadingSpinner from "../components/LoadingSpinner";
import RiskChart from "../components/RiskChart";
import SectorAllocation from "../components/SectorAllocation";
import SummaryCards from "../components/SummaryCards";
import SyncButton from "../components/SyncButton";
import type {
  AllocationResponse,
  CorrelationResponse,
  ExposureResponse,
  Holding,
  PortfolioSummary,
} from "../types/portfolio";
import type { RiskSnapshot } from "../types/trade";

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [allocation, setAllocation] = useState<AllocationResponse | null>(null);
  const [correlation, setCorrelation] = useState<CorrelationResponse | null>(null);
  const [exposure, setExposure] = useState<ExposureResponse | null>(null);
  const [snapshots, setSnapshots] = useState<RiskSnapshot[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, h, a, e] = await Promise.all([
        fetchSummary(),
        fetchHoldings(),
        fetchAllocation(),
        fetchExposure(),
      ]);
      setSummary(s);
      setHoldings(h);
      setAllocation(a);
      setExposure(e);

      // Correlation and snapshots are slower; load separately
      try {
        const c = await fetchCorrelation();
        setCorrelation(c);
      } catch {
        // Non-critical — don't block dashboard
      }
      try {
        const snaps = await fetchSnapshots(30);
        setSnapshots(snaps);
      } catch {
        // Non-critical
      }
    } catch {
      setError("Failed to load portfolio data. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Portfolio Risk Cockpit</h1>
        <SyncButton onSynced={loadData} />
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {correlation && correlation.warnings.length > 0 && (
        <div className="mb-4">
          <ConcentrationBanner warnings={correlation.warnings} />
        </div>
      )}

      {summary && (
        <div className="mb-6">
          <SummaryCards summary={summary} />
        </div>
      )}

      <div className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-gray-800">Holdings</h2>
        <HoldingsTable holdings={holdings} />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {allocation && <SectorAllocation allocation={allocation} />}
        {exposure && <ExposureMeter exposure={exposure} />}
      </div>

      <div className="mb-6">
        <RiskChart snapshots={snapshots} />
      </div>

      {correlation && (
        <div className="mb-6">
          <CorrelationHeatmap correlation={correlation} />
        </div>
      )}
    </div>
  );
}
