import { useCallback, useEffect, useState } from "react";
import { fetchAuthStatus } from "./api/client";
import AlertsPage from "./pages/AlertsPage";
import Dashboard from "./pages/Dashboard";
import JournalPage from "./pages/JournalPage";
import OrdersPage from "./pages/OrdersPage";
import ScannerPage from "./pages/ScannerPage";
import TaxReportPage from "./pages/TaxReportPage";
import TradesPage from "./pages/TradesPage";

type Tab = "dashboard" | "trades" | "alerts" | "scanner" | "journal" | "orders" | "tax";

const tabs: { key: Tab; label: string }[] = [
  { key: "dashboard", label: "Dashboard" },
  { key: "trades", label: "Trades" },
  { key: "orders", label: "Orders" },
  { key: "alerts", label: "Alerts" },
  { key: "scanner", label: "Scanner" },
  { key: "journal", label: "Journal" },
  { key: "tax", label: "Tax" },
];

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  const checkAuth = useCallback(async () => {
    try {
      const status = await fetchAuthStatus();
      setAuthenticated(status);
    } catch {
      setAuthenticated(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // Listen for 401s from any API call
  useEffect(() => {
    function onAuthExpired() {
      setAuthenticated(false);
    }
    window.addEventListener("kite-auth-expired", onAuthExpired);
    return () => window.removeEventListener("kite-auth-expired", onAuthExpired);
  }, []);

  // Re-check auth when window regains focus (user may have logged in via another tab)
  useEffect(() => {
    function onFocus() {
      checkAuth();
    }
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [checkAuth]);

  function handleLogin() {
    window.location.href = "/api/auth/login";
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <nav className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4">
          <div className="flex">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`border-b-2 px-4 py-3 text-sm font-medium ${
                  activeTab === tab.key
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            {authenticated === false && (
              <button
                onClick={handleLogin}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
              >
                Connect Kite
              </button>
            )}
            {authenticated === true && (
              <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-500" />
                Kite Connected
              </span>
            )}
          </div>
        </div>
      </nav>

      {authenticated === false && (
        <div className="border-b border-amber-300 bg-amber-50 px-4 py-3">
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <p className="text-sm text-amber-800">
              Kite session is not active. Portfolio sync, scanner, and live data
              require an active session.
            </p>
            <button
              onClick={handleLogin}
              className="rounded-lg bg-amber-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-700"
            >
              Login to Kite
            </button>
          </div>
        </div>
      )}

      {activeTab === "dashboard" && <Dashboard />}
      {activeTab === "trades" && <TradesPage />}
      {activeTab === "orders" && <OrdersPage />}
      {activeTab === "alerts" && <AlertsPage />}
      {activeTab === "scanner" && <ScannerPage />}
      {activeTab === "journal" && <JournalPage />}
      {activeTab === "tax" && <TaxReportPage />}
    </div>
  );
}

export default App;
