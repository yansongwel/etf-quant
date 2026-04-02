"use client";

import { useEffect, useState } from "react";
import MetricCard from "@/components/MetricCard";
import EquityChart from "@/components/EquityChart";
import DrawdownChart from "@/components/DrawdownChart";
import TradesTable from "@/components/TradesTable";
import { api } from "@/lib/api";
import type { ETFInfo, BacktestResponse, StrategyInfoItem } from "@/lib/api";
import { pct, money, shortDate } from "@/lib/format";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

type StrategyType = "rotation" | "balance" | "grid" | "multifactor";

interface StrategyInfo {
  id: StrategyType;
  name: string;
  description: string;
}

const STRATEGIES: StrategyInfo[] = [
  { id: "rotation", name: "动量轮动", description: "按动量排名在 ETF 间定期切换" },
  { id: "balance", name: "股债平衡", description: "股票/债券 ETF 按目标比例再平衡" },
  { id: "grid", name: "网格交易", description: "在价格网格内高抛低吸" },
  { id: "multifactor", name: "多因子打分", description: "综合动量+价值+波动率排序" },
];

const DEFAULT_SYMBOLS = ["510300", "510500", "510050", "159915", "512010", "512880", "515030"];

export default function BacktestPage() {
  const [etfList, setEtfList] = useState<ETFInfo[]>([]);
  const [strategy, setStrategy] = useState<StrategyType>("rotation");
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [apiStrategies, setApiStrategies] = useState<StrategyInfoItem[]>([]);
  const [compareResult, setCompareResult] = useState<{ label: string; equity: { date: string; value: number }[] } | null>(null);

  // Strategy-specific params
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_SYMBOLS);
  const [lookback, setLookback] = useState(20);
  const [topK, setTopK] = useState(3);
  const [rebalanceDays, setRebalanceDays] = useState(20);
  const [initialCash, setInitialCash] = useState(1_000_000);
  const [commissionRate, setCommissionRate] = useState(0.0002);
  const [slippage, setSlippage] = useState(0.001);
  // Balance-specific
  const [stockSymbol, setStockSymbol] = useState("510300");
  const [bondSymbol, setBondSymbol] = useState("511010");
  const [stockWeight, setStockWeight] = useState(0.6);
  const [driftThreshold, setDriftThreshold] = useState(0.1);
  // Grid-specific
  const [gridSymbol, setGridSymbol] = useState("510300");
  const [gridCount, setGridCount] = useState(10);
  const [gridWidth, setGridWidth] = useState(0.02);
  // MultiFactor-specific
  const [momWeight, setMomWeight] = useState(0.5);
  const [valWeight, setValWeight] = useState(0.3);
  const [volWeight, setVolWeight] = useState(0.2);

  useEffect(() => {
    api.etfList().then(setEtfList).catch(() => {});
    api.backtestStrategies().then(setApiStrategies).catch(() => {});
  }, []);

  const toggleSymbol = (sym: string) => {
    setSymbols((prev) =>
      prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym]
    );
  };

  const runBacktest = async () => {
    setLoading(true);
    setError("");
    const start = Date.now();
    try {
      let res: BacktestResponse;
      const base = { initial_cash: initialCash, commission_rate: commissionRate, slippage };

      if (strategy === "rotation") {
        res = await api.backtestRotation({
          ...base, symbols, lookback, top_k: topK, rebalance_days: rebalanceDays,
        });
      } else if (strategy === "balance") {
        const resp = await fetch("/api/backtest/balance", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...base, stock_symbol: stockSymbol, bond_symbol: bondSymbol,
            stock_weight: stockWeight, drift_threshold: driftThreshold,
          }),
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || "Failed");
        res = await resp.json();
      } else if (strategy === "grid") {
        const resp = await fetch("/api/backtest/grid", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...base, symbol: gridSymbol, grid_count: gridCount, grid_width_pct: gridWidth,
          }),
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || "Failed");
        res = await resp.json();
      } else {
        const resp = await fetch("/api/backtest/multifactor", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...base, symbols, lookback, top_k: topK, rebalance_days: rebalanceDays,
            momentum_weight: momWeight, value_weight: valWeight, volatility_weight: volWeight,
          }),
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || "Failed");
        res = await resp.json();
      }
      setResult(res);
      setElapsed(Date.now() - start);
    } catch (e) {
      setError(e instanceof Error ? e.message : "回测失败");
    } finally {
      setLoading(false);
    }
  };

  const m = result?.metrics;
  const strategyInfo = STRATEGIES.find((s) => s.id === strategy)!;

  return (
    <div>
      <h2 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>策略回测</h2>

      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: "1.5rem" }}>
        {/* Left: Parameters */}
        <div>
          {/* Strategy selector */}
          <div className="card" style={{ marginBottom: "1rem" }}>
            <h3 style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
              选择策略
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              {STRATEGIES.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setStrategy(s.id)}
                  className={`btn ${strategy === s.id ? "btn-primary" : "btn-secondary"}`}
                  style={{ fontSize: "0.8rem", padding: "8px 6px" }}
                >
                  {s.name}
                </button>
              ))}
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 8 }}>
              {strategyInfo.description}
            </p>
          </div>

          {/* Strategy params */}
          <div className="card" style={{ marginBottom: "1rem" }}>
            <h3 style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "0.75rem" }}>
              参数配置
            </h3>

            {/* Symbol selection for rotation / multifactor */}
            {(strategy === "rotation" || strategy === "multifactor") && (
              <div style={{ marginBottom: "0.75rem" }}>
                <label className="metric-label" style={{ display: "block", marginBottom: 4 }}>ETF 池</label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                  {etfList.map((etf) => (
                    <button key={etf.symbol} onClick={() => toggleSymbol(etf.symbol)}
                      style={{
                        padding: "2px 6px", borderRadius: 4, fontSize: "0.7rem",
                        border: `1px solid ${symbols.includes(etf.symbol) ? "var(--accent)" : "var(--border)"}`,
                        background: symbols.includes(etf.symbol) ? "rgba(59,130,246,0.15)" : "transparent",
                        color: symbols.includes(etf.symbol) ? "var(--accent)" : "var(--text-secondary)",
                        cursor: "pointer",
                      }}
                      title={etf.name}
                    >
                      {etf.symbol}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
              {/* Common params */}
              {(strategy === "rotation" || strategy === "multifactor") && (
                <>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>回看周期</label>
                    <input className="input" type="number" value={lookback} onChange={(e) => setLookback(Number(e.target.value))} min={5} max={120} />
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>持仓数</label>
                    <input className="input" type="number" value={topK} onChange={(e) => setTopK(Number(e.target.value))} min={1} max={10} />
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>调仓频率</label>
                    <input className="input" type="number" value={rebalanceDays} onChange={(e) => setRebalanceDays(Number(e.target.value))} min={5} max={60} />
                  </div>
                </>
              )}

              {/* Balance-specific */}
              {strategy === "balance" && (
                <>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>股票 ETF</label>
                    <select className="select" style={{ width: "100%" }} value={stockSymbol} onChange={(e) => setStockSymbol(e.target.value)}>
                      {etfList.filter((e) => e.category !== "债券").map((e) => (
                        <option key={e.symbol} value={e.symbol}>{e.symbol} {e.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>债券 ETF</label>
                    <select className="select" style={{ width: "100%" }} value={bondSymbol} onChange={(e) => setBondSymbol(e.target.value)}>
                      {etfList.filter((e) => e.category === "债券").map((e) => (
                        <option key={e.symbol} value={e.symbol}>{e.symbol} {e.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>股票比例</label>
                    <input className="input" type="number" value={stockWeight} onChange={(e) => setStockWeight(Number(e.target.value))} min={0.1} max={0.9} step={0.1} />
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>漂移阈值</label>
                    <input className="input" type="number" value={driftThreshold} onChange={(e) => setDriftThreshold(Number(e.target.value))} min={0.02} max={0.3} step={0.01} />
                  </div>
                </>
              )}

              {/* Grid-specific */}
              {strategy === "grid" && (
                <>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>交易 ETF</label>
                    <select className="select" style={{ width: "100%" }} value={gridSymbol} onChange={(e) => setGridSymbol(e.target.value)}>
                      {etfList.map((e) => (
                        <option key={e.symbol} value={e.symbol}>{e.symbol} {e.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>网格数</label>
                    <input className="input" type="number" value={gridCount} onChange={(e) => setGridCount(Number(e.target.value))} min={3} max={30} />
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>网格间距 %</label>
                    <input className="input" type="number" value={gridWidth} onChange={(e) => setGridWidth(Number(e.target.value))} min={0.005} max={0.1} step={0.005} />
                  </div>
                </>
              )}

              {/* MultiFactor weights */}
              {strategy === "multifactor" && (
                <>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>动量权重</label>
                    <input className="input" type="number" value={momWeight} onChange={(e) => setMomWeight(Number(e.target.value))} min={0} max={1} step={0.1} />
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>价值权重</label>
                    <input className="input" type="number" value={valWeight} onChange={(e) => setValWeight(Number(e.target.value))} min={0} max={1} step={0.1} />
                  </div>
                  <div>
                    <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>波动率权重</label>
                    <input className="input" type="number" value={volWeight} onChange={(e) => setVolWeight(Number(e.target.value))} min={0} max={1} step={0.1} />
                  </div>
                </>
              )}

              {/* Common trading params */}
              <div>
                <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>初始资金</label>
                <input className="input" type="number" value={initialCash} onChange={(e) => setInitialCash(Number(e.target.value))} min={10000} step={100000} />
              </div>
              <div>
                <label className="metric-label" style={{ display: "block", marginBottom: 3 }}>佣金率</label>
                <input className="input" type="number" value={commissionRate} onChange={(e) => setCommissionRate(Number(e.target.value))} min={0} max={0.01} step={0.0001} />
              </div>
            </div>

            <button className="btn btn-primary" onClick={runBacktest} disabled={loading}
              style={{ width: "100%", marginTop: "1rem", padding: "0.7rem" }}
            >
              {loading ? "运行中..." : `运行 ${strategyInfo.name} 回测`}
            </button>

            {elapsed > 0 && (
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 6, textAlign: "center" }}>
                耗时 {(elapsed / 1000).toFixed(1)}s
              </div>
            )}
          </div>

          {result?.warnings && result.warnings.length > 0 && (
            <div className="card" style={{ borderColor: "var(--yellow)" }}>
              <h4 style={{ fontSize: "0.85rem", color: "var(--yellow)", marginBottom: 6 }}>警告</h4>
              {result.warnings.map((w, i) => (
                <div key={i} style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>{w}</div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Results */}
        <div>
          {error && (
            <div className="card" style={{ borderColor: "var(--red)", marginBottom: "1rem" }}>
              <span style={{ color: "var(--red)" }}>{error}</span>
            </div>
          )}

          {m && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1rem" }}>
              <MetricCard label="总收益" value={pct(m.total_return)} className={m.total_return >= 0 ? "metric-positive" : "metric-negative"} />
              <MetricCard label="年化收益" value={pct(m.annualized_return)} className={m.annualized_return >= 0 ? "metric-positive" : "metric-negative"} />
              <MetricCard label="最大回撤" value={pct(m.max_drawdown)} className="metric-negative" />
              <MetricCard label="夏普比率" value={m.sharpe_ratio.toFixed(2)} />
              <MetricCard label="Calmar" value={m.calmar_ratio.toFixed(2)} />
              <MetricCard label="胜率" value={pct(m.win_rate)} />
              <MetricCard label="交易次数" value={String(m.total_trades)} />
              <MetricCard label="终值" value={money(result!.equity_curve.data[result!.equity_curve.data.length - 1]?.value ?? 0)} />
            </div>
          )}

          {/* Save for comparison + comparison chart */}
          {result && (
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <button
                className="btn btn-secondary"
                style={{ fontSize: "0.75rem" }}
                onClick={() => {
                  setCompareResult({
                    label: `${strategyInfo.name} (基准)`,
                    equity: result.equity_curve.data,
                  });
                }}
              >
                保存为对比基准
              </button>
              {compareResult && (
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}
                  onClick={() => setCompareResult(null)}
                >
                  清除基准
                </button>
              )}
              {compareResult && (
                <span style={{ fontSize: "0.7rem", color: "var(--text-secondary)", display: "flex", alignItems: "center" }}>
                  对比: {compareResult.label}
                </span>
              )}
            </div>
          )}

          {/* Equity chart (with optional comparison overlay) */}
          {compareResult && result ? (
            <div className="card" style={{ marginBottom: "1rem" }}>
              <h3 style={{ fontSize: "0.9rem", marginBottom: "0.75rem", color: "var(--text-secondary)" }}>
                净值对比
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart
                  data={(() => {
                    const baseMap = new Map(compareResult.equity.map((d) => [d.date, d.value]));
                    const currentMap = new Map(result.equity_curve.data.map((d) => [d.date, d.value]));
                    const allDates = [...new Set([...baseMap.keys(), ...currentMap.keys()])].sort();
                    return allDates.map((date) => ({
                      date,
                      baseline: baseMap.get(date) ?? null,
                      current: currentMap.get(date) ?? null,
                    }));
                  })()}
                >
                  <defs>
                    <linearGradient id="cmpGrad1" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="cmpGrad2" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 10, fill: "#64748b" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#64748b" }} tickFormatter={(v: number) => `¥${(v / 10000).toFixed(0)}万`} />
                  <Tooltip
                    contentStyle={{ background: "rgba(15,23,42,0.95)", border: "1px solid #334155", borderRadius: 8, fontSize: "0.75rem" }}
                    labelStyle={{ color: "#94a3b8" }}
                  />
                  <Area type="monotone" dataKey="baseline" stroke="#3b82f6" strokeWidth={1.5} fill="url(#cmpGrad1)" dot={false} connectNulls />
                  <Area type="monotone" dataKey="current" stroke="#22c55e" strokeWidth={2} fill="url(#cmpGrad2)" dot={false} connectNulls />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div style={{ marginBottom: "1rem" }}>
              <EquityChart data={result?.equity_curve.data ?? []} height={300} />
            </div>
          )}
          <div style={{ marginBottom: "1rem" }}>
            <DrawdownChart equityData={result?.equity_curve.data ?? []} height={180} />
          </div>
          <TradesTable trades={result?.trades.data ?? []} maxRows={50} />
        </div>
      </div>
    </div>
  );
}
