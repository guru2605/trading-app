import { useCallback, useEffect, useState } from "react";
import {
  activatePanic,
  checkMargins,
  createRule,
  deleteRule,
  evaluateRules,
  fetchRules,
  fetchSafetyStatus,
  placeOrder,
  updateRule,
  updateSafetyConfig,
} from "../api/orders";
import LoadingSpinner from "../components/LoadingSpinner";
import type {
  OrderMarginResponse,
  OrderPlaceResponse,
  OrderRule,
  RuleEvaluateResult,
  SafetyStatusResponse,
} from "../types/orders";

export default function OrdersPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Safety status
  const [safetyStatus, setSafetyStatus] = useState<SafetyStatusResponse | null>(null);

  // Order form
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [txnType, setTxnType] = useState("BUY");
  const [quantity, setQuantity] = useState("1");
  const [price, setPrice] = useState("");
  const [product, setProduct] = useState("CNC");
  const [orderType, setOrderType] = useState("MARKET");
  const [placing, setPlacing] = useState(false);
  const [orderResult, setOrderResult] = useState<OrderPlaceResponse | null>(null);
  const [marginPreview, setMarginPreview] = useState<OrderMarginResponse | null>(null);

  // Rules
  const [rules, setRules] = useState<OrderRule[]>([]);
  const [ruleName, setRuleName] = useState("");
  const [ruleSymbol, setRuleSymbol] = useState("");
  const [ruleCondition, setRuleCondition] = useState("");
  const [ruleQuantity, setRuleQuantity] = useState("1");
  const [creatingRule, setCreatingRule] = useState(false);
  const [evalResults, setEvalResults] = useState<RuleEvaluateResult[] | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  // Safety config editing
  const [editingConfig, setEditingConfig] = useState(false);
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({});

  // Panic confirmation
  const [showPanicConfirm, setShowPanicConfirm] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [status, rulesList] = await Promise.all([
        fetchSafetyStatus(),
        fetchRules(),
      ]);
      setSafetyStatus(status);
      setRules(rulesList);
    } catch {
      setError("Failed to load data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handlePlaceOrder() {
    if (!symbol || !quantity) return;
    setPlacing(true);
    setOrderResult(null);
    try {
      const result = await placeOrder({
        tradingsymbol: symbol.toUpperCase(),
        exchange,
        transaction_type: txnType,
        quantity: parseInt(quantity),
        price: price ? parseFloat(price) : null,
        product,
        order_type: orderType,
      });
      setOrderResult(result);
      await loadData();
    } catch {
      setError("Failed to place order.");
    } finally {
      setPlacing(false);
    }
  }

  async function handleCheckMargin() {
    if (!symbol || !quantity) return;
    try {
      const result = await checkMargins({
        tradingsymbol: symbol.toUpperCase(),
        exchange,
        transaction_type: txnType,
        quantity: parseInt(quantity),
        price: price ? parseFloat(price) : undefined,
        product,
        order_type: orderType,
      });
      setMarginPreview(result);
    } catch {
      setError("Failed to check margins.");
    }
  }

  async function handlePanic() {
    try {
      await activatePanic();
      setShowPanicConfirm(false);
      await loadData();
    } catch {
      setError("Failed to activate panic mode.");
    }
  }

  async function handleDeactivatePanic() {
    try {
      await updateSafetyConfig({ panic_mode: false });
      await loadData();
    } catch {
      setError("Failed to deactivate panic mode.");
    }
  }

  async function handleCreateRule() {
    if (!ruleName || !ruleSymbol) return;
    setCreatingRule(true);
    try {
      await createRule({
        name: ruleName,
        tradingsymbol: ruleSymbol.toUpperCase(),
        exchange: "NSE",
        transaction_type: "BUY",
        quantity: parseInt(ruleQuantity) || 1,
        condition: ruleCondition,
      });
      setRuleName("");
      setRuleSymbol("");
      setRuleCondition("");
      setRuleQuantity("1");
      await loadData();
    } catch {
      setError("Failed to create rule.");
    } finally {
      setCreatingRule(false);
    }
  }

  async function handleDeleteRule(id: number) {
    try {
      await deleteRule(id);
      await loadData();
    } catch {
      setError("Failed to delete rule.");
    }
  }

  async function handleToggleRule(rule: OrderRule) {
    try {
      await updateRule(rule.id, { is_active: !rule.is_active });
      await loadData();
    } catch {
      setError("Failed to update rule.");
    }
  }

  async function handleEvaluateRules() {
    setEvaluating(true);
    setEvalResults(null);
    try {
      const results = await evaluateRules();
      setEvalResults(results);
      await loadData();
    } catch {
      setError("Failed to evaluate rules.");
    } finally {
      setEvaluating(false);
    }
  }

  function startEditConfig() {
    if (!safetyStatus) return;
    const c = safetyStatus.config;
    setConfigDraft({
      max_daily_loss: String(c.max_daily_loss),
      max_order_value: String(c.max_order_value),
      max_orders_per_day: String(c.max_orders_per_day),
      max_position_pct: String(c.max_position_pct),
      loss_cooldown_count: String(c.loss_cooldown_count),
      loss_cooldown_minutes: String(c.loss_cooldown_minutes),
      vix_kill_threshold: String(c.vix_kill_threshold),
      dry_run: String(c.dry_run),
    });
    setEditingConfig(true);
  }

  async function handleSaveConfig() {
    try {
      const updates: Record<string, unknown> = {};
      for (const [key, val] of Object.entries(configDraft)) {
        if (key === "dry_run") {
          updates[key] = val === "true";
        } else {
          updates[key] = parseFloat(val);
        }
      }
      await updateSafetyConfig(updates);
      setEditingConfig(false);
      await loadData();
    } catch {
      setError("Failed to save config.");
    }
  }

  if (loading) return <LoadingSpinner />;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Orders & Risk</h1>
        <div className="flex gap-2">
          {safetyStatus?.panic_active ? (
            <button
              onClick={handleDeactivatePanic}
              className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
            >
              Deactivate Panic
            </button>
          ) : (
            <button
              onClick={() => setShowPanicConfirm(true)}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-bold text-white hover:bg-red-700"
            >
              PANIC
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">
            dismiss
          </button>
        </div>
      )}

      {/* Panic confirmation dialog */}
      {showPanicConfirm && (
        <div className="mb-4 rounded-lg border-2 border-red-500 bg-red-50 p-4">
          <p className="mb-3 font-bold text-red-800">
            Are you sure? This will block ALL orders immediately.
          </p>
          <div className="flex gap-2">
            <button
              onClick={handlePanic}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-bold text-white hover:bg-red-700"
            >
              Yes, activate panic mode
            </button>
            <button
              onClick={() => setShowPanicConfirm(false)}
              className="rounded-lg bg-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-400"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Risk Status Panel */}
      {safetyStatus && (
        <div className="mb-6 rounded-lg bg-white p-4 shadow">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-800">
              Risk Status
            </h2>
            <div className="flex items-center gap-2">
              <span
                className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${
                  safetyStatus.config.dry_run
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-green-100 text-green-700"
                }`}
              >
                {safetyStatus.config.dry_run ? "DRY RUN" : "LIVE"}
              </span>
              {safetyStatus.panic_active && (
                <span className="inline-block rounded bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
                  PANIC
                </span>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <div>
            
              <span className="text-gray-500">Orders Today</span>
              <p className="font-medium">
                {safetyStatus.orders_today} / {safetyStatus.config.max_orders_per_day}
              </p>
            </div>
            <div>
              <span className="text-gray-500">Realized P&L</span>
              <p
                className={`font-medium ${
                  safetyStatus.realized_pnl_today >= 0
                    ? "text-green-600"
                    : "text-red-600"
                }`}
              >
                {safetyStatus.realized_pnl_today.toFixed(2)}
              </p>
            </div>
            <div>
              <span className="text-gray-500">Max Daily Loss</span>
              <p className="font-medium">
                {safetyStatus.config.max_daily_loss.toFixed(0)}
              </p>
            </div>
            <div>
              <span className="text-gray-500">Trading Hours</span>
              <p className="font-medium">
                {safetyStatus.trading_hours_active ? "Active" : "Closed"}
              </p>
            </div>
          </div>
          <div className="mt-3">
            <button
              onClick={editingConfig ? handleSaveConfig : startEditConfig}
              className="text-sm text-blue-600 hover:underline"
            >
              {editingConfig ? "Save Config" : "Edit Config"}
            </button>
            {editingConfig && (
              <button
                onClick={() => setEditingConfig(false)}
                className="ml-3 text-sm text-gray-500 hover:underline"
              >
                Cancel
              </button>
            )}
          </div>
          {editingConfig && (
            <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
              {Object.entries(configDraft).map(([key, val]) => (
                <div key={key}>
                  <label className="block text-xs text-gray-500">
                    {key.replace(/_/g, " ")}
                  </label>
                  {key === "dry_run" ? (
                    <select
                      value={val}
                      onChange={(e) =>
                        setConfigDraft({ ...configDraft, [key]: e.target.value })
                      }
                      className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                    >
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  ) : (
                    <input
                      type="number"
                      value={val}
                      onChange={(e) =>
                        setConfigDraft({ ...configDraft, [key]: e.target.value })
                      }
                      className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Order Form */}
      <div className="mb-6 rounded-lg bg-white p-4 shadow">
        <h2 className="mb-3 text-lg font-semibold text-gray-800">
          Place Order
        </h2>
        <div className="flex flex-wrap gap-3">
          <input
            type="text"
            placeholder="Symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <select
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
          </select>
          <select
            value={txnType}
            onChange={(e) => setTxnType(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
          <input
            type="number"
            placeholder="Qty"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="number"
            placeholder="Price"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-28 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <select
            value={product}
            onChange={(e) => setProduct(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="CNC">CNC</option>
            <option value="MIS">MIS</option>
            <option value="NRML">NRML</option>
          </select>
          <select
            value={orderType}
            onChange={(e) => setOrderType(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="MARKET">MARKET</option>
            <option value="LIMIT">LIMIT</option>
            <option value="SL">SL</option>
            <option value="SL-M">SL-M</option>
          </select>
          <button
            onClick={handleCheckMargin}
            disabled={!symbol || !quantity}
            className="rounded-lg bg-gray-600 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            Check Margin
          </button>
          <button
            onClick={handlePlaceOrder}
            disabled={placing || !symbol || !quantity}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${
              txnType === "BUY"
                ? "bg-green-600 hover:bg-green-700"
                : "bg-red-600 hover:bg-red-700"
            }`}
          >
            {placing ? "Placing..." : `Place ${txnType}`}
          </button>
        </div>

        {marginPreview && (
          <div className="mt-3 rounded border border-blue-200 bg-blue-50 p-3 text-sm">
            Margin required: <strong>{marginPreview.total.toFixed(2)}</strong>
            {marginPreview.available !== null && (
              <>
                {" "}| Available: <strong>{marginPreview.available.toFixed(2)}</strong>
                {" "}|{" "}
                <span className={marginPreview.sufficient ? "text-green-600" : "text-red-600"}>
                  {marginPreview.sufficient ? "Sufficient" : "Insufficient"}
                </span>
              </>
            )}
          </div>
        )}

        {orderResult && (
          <div
            className={`mt-3 rounded border p-3 text-sm ${
              orderResult.status === "SUCCESS"
                ? "border-green-200 bg-green-50"
                : "border-red-200 bg-red-50"
            }`}
          >
            <p className="font-medium">
              Status: {orderResult.status}
              {orderResult.dry_run && " (DRY RUN)"}
              {orderResult.order_id && ` | Order ID: ${orderResult.order_id}`}
            </p>
            {orderResult.risk_checks.length > 0 && (
              <div className="mt-2">
                {orderResult.risk_checks.map((check) => (
                  <div
                    key={check.stage}
                    className={`text-xs ${
                      check.passed ? "text-green-700" : "text-red-700"
                    }`}
                  >
                    {check.passed ? "PASS" : "FAIL"} {check.stage}: {check.reason}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Rules */}
      <div className="mb-6 rounded-lg bg-white p-4 shadow">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800">Order Rules</h2>
          <button
            onClick={handleEvaluateRules}
            disabled={evaluating}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {evaluating ? "Evaluating..." : "Evaluate Rules"}
          </button>
        </div>

        {evalResults && (
          <div className="mb-3 rounded border border-blue-200 bg-blue-50 p-3 text-sm">
            {evalResults.map((r) => (
              <div key={r.rule_id}>
                <strong>{r.name}</strong>:{" "}
                {r.triggered ? (
                  <span className="text-green-700">
                    Triggered (order: {r.order_status})
                  </span>
                ) : (
                  <span className="text-gray-500">{r.reason}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* New rule form */}
        <div className="mb-4 flex flex-wrap gap-3">
          <input
            type="text"
            placeholder="Rule name"
            value={ruleName}
            onChange={(e) => setRuleName(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="text"
            placeholder="Symbol"
            value={ruleSymbol}
            onChange={(e) => setRuleSymbol(e.target.value.toUpperCase())}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="number"
            placeholder="Qty"
            value={ruleQuantity}
            onChange={(e) => setRuleQuantity(e.target.value)}
            className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="text"
            placeholder='Condition JSON e.g. {"type":"price_below","value":1500}'
            value={ruleCondition}
            onChange={(e) => setRuleCondition(e.target.value)}
            className="min-w-[300px] rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={handleCreateRule}
            disabled={creatingRule || !ruleName || !ruleSymbol}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {creatingRule ? "Creating..." : "Create Rule"}
          </button>
        </div>

        {/* Rules table */}
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Symbol</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3">Condition</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Last Triggered</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rules.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{r.name}</td>
                  <td className="px-4 py-3">{r.tradingsymbol}</td>
                  <td className="px-4 py-3">{r.transaction_type}</td>
                  <td className="px-4 py-3 text-right">{r.quantity}</td>
                  <td className="max-w-[200px] truncate px-4 py-3 text-xs text-gray-500">
                    {r.condition}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${
                        r.is_active
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {r.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {r.last_triggered_at
                      ? new Date(r.last_triggered_at).toLocaleString("en-IN")
                      : "-"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleToggleRule(r)}
                        className="text-sm text-blue-600 hover:underline"
                      >
                        {r.is_active ? "Pause" : "Resume"}
                      </button>
                      <button
                        onClick={() => handleDeleteRule(r.id)}
                        className="text-sm text-red-600 hover:underline"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {rules.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="px-4 py-8 text-center text-gray-400"
                  >
                    No rules yet. Create one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
