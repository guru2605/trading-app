import { useState } from "react";
import { syncHoldings } from "../api/portfolio";

interface Props {
  onSynced: () => void;
}

export default function SyncButton({ onSynced }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSync() {
    setLoading(true);
    setMessage(null);
    try {
      const result = await syncHoldings();
      setMessage(result.message);
      onSynced();
    } catch {
      setMessage("Sync failed. Check Kite connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleSync}
        disabled={loading}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "Syncing..." : "Sync Holdings"}
      </button>
      {message && <span className="text-sm text-gray-600">{message}</span>}
    </div>
  );
}
