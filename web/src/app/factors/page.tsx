"use client";

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import { api } from "@/lib/api";
import type { ETFInfo, FactorResponse, FactorCompareResponse } from "@/lib/api";
import { shortDate } from "@/lib/format";
import CorrelationHeatmap from "@/components/CorrelationHeatmap";

const CATEGORIES = [
  { value: "momentum", label: "动量因子" },
  { value: "value", label: "价值因子" },
  { value: "volatility", label: "波动率因子" },
];

const COLORS = ["#3b82f6", "#22c55e", "#eab308", "#ef4444", "#a855f7", "#ec4899", "#06b6d4", "#f97316"];

export default function FactorsPage() {
  const [etfList, setEtfList] = useState<ETFInfo[]>([]);
  const [symbol, setSymbol] = useState("510300");
  const [category, setCategory] = useState("momentum");
  const [factorData, setFactorData] = useState<FactorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedFactors, setSelectedFactors] = useState<Set<string>>(new Set());
  const [showCompare, setShowCompare] = useState(false);
  const [compareSymbols, setCompareSymbols] = useState<Set<string>>(new Set(["510300", "510500"]));
  const [compareData, setCompareData] = useState<FactorCompareResponse | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [corrData, setCorrData] = useState<{ factors: string[]; matrix: number[][] } | null>(null);
  const [corrLoading, setCorrLoading] = useState(false);

  const toggleCompareSymbol = (sym: string) => {
    setCompareSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym);
      else next.add(sym);
      return next;
    });
  };

  const runCompare = async () => {
    if (compareSymbols.size < 2) return;
    setCompareLoading(true);
    try {
      const res = await api.factorsCompare(Array.from(compareSymbols), category);
      setCompareData(res);
    } catch {
      setCompareData(null);
    } finally {
      setCompareLoading(false);
    }
  };

  useEffect(() => {
    api.etfList().then(setEtfList).catch(() => {});
  }, []);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    setError("");
    api
      .factors(symbol, category, 120)
      .then((r) => {
        setFactorData(r);
        // Auto-select first 3 factors
        setSelectedFactors(new Set(r.factors.slice(0, 3)));
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "加载失败");
        setFactorData(null);
      })
      .finally(() => setLoading(false));
  }, [symbol, category]);

  const toggleFactor = (f: string) => {
    setSelectedFactors((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>因子分析</h2>
        <button
          className={`btn ${showCompare ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setShowCompare(!showCompare)}
        >
          {showCompare ? "隐藏对比" : "多ETF因子对比"}
        </button>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: "1rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <select className="select" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          {etfList.map((etf) => (
            <option key={etf.symbol} value={etf.symbol}>
              {etf.symbol} {etf.name}
            </option>
          ))}
        </select>

        {CATEGORIES.map((cat) => (
          <button
            key={cat.value}
            className={`btn ${category === cat.value ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setCategory(cat.value)}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--red)", marginBottom: "1rem" }}>
          <span style={{ color: "var(--red)" }}>{error}</span>
        </div>
      )}

      {/* Factor toggles */}
      {factorData && (
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
          {factorData.factors.map((f, i) => (
            <button
              key={f}
              onClick={() => toggleFactor(f)}
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                fontSize: "0.8rem",
                border: `1px solid ${selectedFactors.has(f) ? COLORS[i % COLORS.length] : "var(--border)"}`,
                background: selectedFactors.has(f) ? `${COLORS[i % COLORS.length]}22` : "transparent",
                color: selectedFactors.has(f) ? COLORS[i % COLORS.length] : "var(--text-secondary)",
                cursor: "pointer",
              }}
            >
              {f}
            </button>
          ))}
        </div>
      )}

      {/* Chart */}
      {loading ? (
        <div className="card" style={{ height: 400, display: "flex", alignItems: "center", justifyContent: "center" }}>
          计算中...
        </div>
      ) : factorData && factorData.data.length > 0 ? (
        <div className="card">
          <ResponsiveContainer width="100%" height={450}>
            <LineChart data={factorData.data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tickFormatter={shortDate} stroke="#64748b" fontSize={11} tickLine={false} />
              <YAxis stroke="#64748b" fontSize={11} tickLine={false} width={60} />
              <Tooltip
                contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
              />
              <Legend />
              {factorData.factors
                .filter((f) => selectedFactors.has(f))
                .map((f, i) => (
                  <Line
                    key={f}
                    type="monotone"
                    dataKey={f}
                    stroke={COLORS[factorData.factors.indexOf(f) % COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                  />
                ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="card" style={{ height: 400, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ color: "var(--text-secondary)" }}>选择 ETF 和因子类别查看</span>
        </div>
      )}

      {/* Factor data table */}
      {factorData && factorData.data.length > 0 && (
        <div className="card" style={{ marginTop: "1.5rem", overflow: "auto" }}>
          <h3 style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
            因子数据（最近 20 条）
          </h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>日期</th>
                {factorData.factors
                  .filter((f) => selectedFactors.has(f))
                  .map((f) => (
                    <th key={f}>{f}</th>
                  ))}
              </tr>
            </thead>
            <tbody>
              {factorData.data.slice(-20).reverse().map((row, i) => (
                <tr key={i}>
                  <td>{row.date}</td>
                  {factorData.factors
                    .filter((f) => selectedFactors.has(f))
                    .map((f) => (
                      <td key={f} style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                        {row[f] != null ? Number(row[f]).toFixed(4) : "-"}
                      </td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Factor Compare Section */}
      {showCompare && (
        <div className="card" style={{ marginTop: "1.5rem" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.75rem" }}>多 ETF 因子对比</h3>
          <div style={{ marginBottom: "0.75rem" }}>
            <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: 4 }}>
              选择 ETF（至少 2 只）
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {etfList.map((etf) => (
                <button
                  key={etf.symbol}
                  onClick={() => toggleCompareSymbol(etf.symbol)}
                  style={{
                    padding: "3px 8px", borderRadius: 4, fontSize: "0.75rem",
                    border: `1px solid ${compareSymbols.has(etf.symbol) ? "var(--accent)" : "var(--border)"}`,
                    background: compareSymbols.has(etf.symbol) ? "rgba(59,130,246,0.15)" : "transparent",
                    color: compareSymbols.has(etf.symbol) ? "var(--accent)" : "var(--text-secondary)",
                    cursor: "pointer",
                  }}
                  title={etf.name}
                >
                  {etf.symbol}
                </button>
              ))}
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={runCompare}
            disabled={compareLoading || compareSymbols.size < 2}
            style={{ marginBottom: "1rem" }}
          >
            {compareLoading ? "对比中..." : `对比 ${compareSymbols.size} 只 ETF 的 ${CATEGORIES.find(c => c.value === category)?.label || category}`}
          </button>

          {compareData && compareData.data.length > 0 && (
            <div style={{ overflow: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    {compareData.factors.map((f) => (
                      <th key={f}>{f}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compareData.data.map((row) => (
                    <tr key={row.symbol as string}>
                      <td style={{ fontFamily: "monospace", fontWeight: 700 }}>{row.symbol}</td>
                      {compareData.factors.map((f) => {
                        const val = row[f];
                        return (
                          <td key={f} style={{
                            fontFamily: "monospace", fontSize: "0.8rem",
                            color: typeof val === "number" && val > 0 ? "var(--green)" : typeof val === "number" && val < 0 ? "var(--red)" : "inherit",
                            fontWeight: 600,
                          }}>
                            {val != null ? Number(val).toFixed(4) : "-"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              {compareData.missing.length > 0 && (
                <div style={{ fontSize: "0.75rem", color: "var(--yellow)", marginTop: 6 }}>
                  缺少数据: {compareData.missing.join(", ")}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ─── Correlation Heatmap ─── */}
      <div className="card" style={{ padding: "1rem", marginTop: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
          <div>
            <div style={{ fontSize: "1rem", fontWeight: 700 }}>因子相关性矩阵</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 2 }}>
              {symbol} · 所有因子类别 · 120 日 Pearson 相关系数
            </div>
          </div>
          <button
            className="btn btn-secondary"
            onClick={async () => {
              setCorrLoading(true);
              try {
                const res = await fetch(`/api/factors/correlation/${symbol}?tail=120`);
                if (res.ok) setCorrData(await res.json());
              } catch { /* silent */ }
              finally { setCorrLoading(false); }
            }}
            disabled={corrLoading}
          >
            {corrLoading ? "计算中..." : corrData ? "刷新矩阵" : "计算相关性"}
          </button>
        </div>
        {corrData && <CorrelationHeatmap factors={corrData.factors} matrix={corrData.matrix} />}
        {!corrData && !corrLoading && (
          <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
            点击上方按钮计算因子间的相关性矩阵
          </div>
        )}
      </div>
    </div>
  );
}
