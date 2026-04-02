"use client";

import { useEffect, useState, useCallback } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";

interface FlowSignal {
  symbol: string;
  name: string;
  flow_type: string;
  volume_ratio: number;
  amount_ratio: number;
  price_change: number;
  turnover: number;
  volume_trend_5d: number;
  confidence: number;
  label: string;
  advice: string;
  details: string[];
}

interface FlowScanResponse {
  total_scanned: number;
  abnormal_count: number;
  signals: FlowSignal[];
}

const FLOW_COLORS: Record<string, string> = {
  accumulation: "#22c55e",
  distribution: "#ef4444",
  breakout_buy: "#3b82f6",
  panic_sell: "#f97316",
  normal: "#64748b",
};

const FLOW_BG: Record<string, string> = {
  accumulation: "rgba(34,197,94,0.08)",
  distribution: "rgba(239,68,68,0.08)",
  breakout_buy: "rgba(59,130,246,0.08)",
  panic_sell: "rgba(249,115,22,0.08)",
  normal: "transparent",
};

export default function FlowPage() {
  const [data, setData] = useState<FlowScanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [detail, setDetail] = useState<FlowSignal | null>(null);
  const [filter, setFilter] = useState<string>("all"); // all, abnormal

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/flow/scan");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const loadDetail = async (symbol: string) => {
    if (selectedSymbol === symbol) {
      setSelectedSymbol(null);
      setDetail(null);
      return;
    }
    setSelectedSymbol(symbol);
    try {
      const res = await fetch(`/api/flow/detail/${symbol}`);
      setDetail(await res.json());
    } catch {
      setDetail(null);
    }
  };

  const signals = data?.signals ?? [];
  const filtered = filter === "abnormal"
    ? signals.filter((s) => s.flow_type !== "normal")
    : signals;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>机构大单检测</h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 4 }}>
            通过成交量异常、量价背离检测机构资金动向 | 扫描 {data?.total_scanned || 0} 只 ETF
            {(data as unknown as { generated_at?: string })?.generated_at && (
              <span style={{ marginLeft: 6, color: "var(--text-tertiary)" }}>
                · {(data as unknown as { generated_at: string }).generated_at} CST
              </span>
            )}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            className={`btn ${filter === "all" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setFilter("all")}
          >
            全部 ({signals.length})
          </button>
          <button
            className={`btn ${filter === "abnormal" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setFilter("abnormal")}
          >
            异常 ({data?.abnormal_count || 0})
          </button>
          <button className="btn btn-secondary" onClick={refresh} disabled={loading}>
            {loading ? "扫描中..." : "重新扫描"}
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={`大单检测加载失败: ${error}`} onRetry={refresh} />}
      {loading && !data && <LoadingSkeleton rows={4} height={80} />}

      {/* Summary cards */}
      {data && (
        <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem" }}>
          {[
            { type: "accumulation", label: "疑似吸筹", icon: "🟢" },
            { type: "distribution", label: "疑似出货", icon: "🔴" },
            { type: "breakout_buy", label: "放量突破", icon: "🔵" },
            { type: "panic_sell", label: "恐慌抛售", icon: "⚠️" },
          ].map((item) => {
            const count = signals.filter((s) => s.flow_type === item.type).length;
            return (
              <div
                key={item.type}
                className="card"
                style={{
                  flex: 1, textAlign: "center",
                  borderColor: count > 0 ? FLOW_COLORS[item.type] : "var(--border)",
                  borderWidth: count > 0 ? 2 : 1,
                }}
              >
                <div style={{ fontSize: "1.5rem" }}>{item.icon}</div>
                <div style={{ fontSize: "1.5rem", fontWeight: 800, color: FLOW_COLORS[item.type] }}>{count}</div>
                <div className="metric-label">{item.label}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Volume Ratio Chart */}
      {signals.length > 0 && (
        <div className="card" style={{ padding: "0.75rem 1rem", marginBottom: "1rem" }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: "0.5rem" }}>
            量比分布（异常红色 · 正常灰色 · 基准线=1.5x）
          </div>
          <ResponsiveContainer width="100%" height={Math.max(160, signals.length * 28)}>
            <BarChart
              data={[...signals].sort((a, b) => b.volume_ratio - a.volume_ratio)}
              layout="vertical"
              margin={{ top: 0, right: 20, bottom: 0, left: 75 }}
            >
              <XAxis type="number" tick={{ fontSize: 10, fill: "#64748b" }} tickFormatter={(v: number) => `${v}x`} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "#94a3b8" }} width={70} />
              <ReferenceLine x={1.5} stroke="#f59e0b" strokeDasharray="4 3" strokeWidth={1} label={{ value: "1.5x", position: "top", fontSize: 9, fill: "#f59e0b" }} />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.[0]) return null;
                  const d = payload[0].payload as FlowSignal;
                  return (
                    <div style={{ background: "rgba(15,23,42,0.95)", borderRadius: 8, padding: "8px 12px", fontSize: "0.75rem", border: `1px solid ${FLOW_COLORS[d.flow_type]}44` }}>
                      <div style={{ fontWeight: 700 }}>{d.name} ({d.symbol})</div>
                      <div>量比: <strong style={{ color: d.volume_ratio >= 2 ? "#ef4444" : d.volume_ratio >= 1.5 ? "#f59e0b" : "#64748b" }}>{d.volume_ratio}x</strong></div>
                      <div>涨跌: <strong style={{ color: d.price_change > 0 ? "#4ade80" : d.price_change < 0 ? "#f87171" : "#64748b" }}>{d.price_change > 0 ? "+" : ""}{d.price_change}%</strong></div>
                      <div style={{ color: FLOW_COLORS[d.flow_type], fontWeight: 600 }}>{d.label}</div>
                    </div>
                  );
                }}
              />
              <Bar dataKey="volume_ratio" barSize={16} radius={[0, 4, 4, 0]}>
                {[...signals].sort((a, b) => b.volume_ratio - a.volume_ratio).map((s, i) => (
                  <Cell key={i} fill={s.flow_type !== "normal" ? FLOW_COLORS[s.flow_type] : "#334155"} fillOpacity={s.flow_type !== "normal" ? 0.8 : 0.4} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Detail panel */}
      {detail && (
        <div className="card" style={{ marginBottom: "1.5rem", borderColor: FLOW_COLORS[detail.flow_type], borderWidth: 2, background: FLOW_BG[detail.flow_type] }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div>
              <span style={{ fontWeight: 800, fontSize: "1.3rem", fontFamily: "monospace" }}>{detail.symbol}</span>
              <span style={{ marginLeft: 8, fontSize: "0.9rem", color: "var(--text-secondary)" }}>{detail.name}</span>
              <span style={{ marginLeft: 12, padding: "4px 10px", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700, color: "white", background: FLOW_COLORS[detail.flow_type] }}>
                {detail.label}
              </span>
            </div>
            <button className="btn btn-secondary" onClick={() => { setSelectedSymbol(null); setDetail(null); }} style={{ padding: "4px 12px" }}>
              关闭
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "0.75rem", marginBottom: "1rem" }}>
            {[
              { label: "量比(vs 20日)", value: `${detail.volume_ratio}x`, color: detail.volume_ratio >= 2 ? "var(--red)" : detail.volume_ratio >= 1.5 ? "var(--yellow)" : "var(--green)" },
              { label: "额比(vs 20日)", value: `${detail.amount_ratio}x`, color: detail.amount_ratio >= 2 ? "var(--red)" : "inherit" },
              { label: "涨跌幅", value: `${detail.price_change > 0 ? "+" : ""}${detail.price_change}%`, color: detail.price_change > 0 ? "var(--green)" : detail.price_change < 0 ? "var(--red)" : "inherit" },
              { label: "换手率", value: `${detail.turnover}%`, color: detail.turnover > 5 ? "var(--yellow)" : "inherit" },
              { label: "置信度", value: `${detail.confidence}%`, color: detail.confidence > 60 ? "var(--green)" : "var(--text-secondary)" },
            ].map((m, i) => (
              <div key={i} style={{ background: "var(--bg-primary)", borderRadius: 8, padding: "10px", textAlign: "center" }}>
                <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>{m.label}</div>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: m.color }}>{m.value}</div>
              </div>
            ))}
          </div>

          <div style={{ marginBottom: "0.75rem" }}>
            <h4 style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: 6 }}>观察详情</h4>
            {detail.details.map((d, i) => (
              <div key={i} style={{ fontSize: "0.85rem", padding: "4px 0", color: "var(--text-secondary)" }}>
                {d}
              </div>
            ))}
          </div>

          <div style={{ padding: "10px 12px", background: `${FLOW_COLORS[detail.flow_type]}15`, borderRadius: 8, border: `1px solid ${FLOW_COLORS[detail.flow_type]}40` }}>
            <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>操作建议: </span>
            <span style={{ fontSize: "0.85rem" }}>{detail.advice}</span>
          </div>
        </div>
      )}

      {/* Signal grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "0.75rem" }}>
        {filtered.map((s) => (
          <div
            key={s.symbol}
            className="card"
            onClick={() => loadDetail(s.symbol)}
            style={{
              cursor: "pointer",
              background: FLOW_BG[s.flow_type],
              borderColor: selectedSymbol === s.symbol ? FLOW_COLORS[s.flow_type] : s.flow_type !== "normal" ? `${FLOW_COLORS[s.flow_type]}80` : "var(--border)",
              borderWidth: selectedSymbol === s.symbol ? 2 : 1,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <div>
                <span style={{ fontWeight: 700, fontSize: "1rem", fontFamily: "monospace" }}>{s.symbol}</span>
                <span style={{ marginLeft: 6, fontSize: "0.8rem", color: "var(--text-secondary)" }}>{s.name}</span>
              </div>
              <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, color: "white", background: FLOW_COLORS[s.flow_type] }}>
                {s.label.replace(/[🟢🔴🔵⚠️⚪]\s?/, "")}
              </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, fontSize: "0.8rem" }}>
              <div>
                <span style={{ color: "var(--text-secondary)" }}>量比 </span>
                <strong style={{ color: s.volume_ratio >= 2 ? "var(--red)" : s.volume_ratio >= 1.5 ? "var(--yellow)" : "inherit" }}>
                  {s.volume_ratio}x
                </strong>
              </div>
              <div>
                <span style={{ color: "var(--text-secondary)" }}>涨跌 </span>
                <strong style={{ color: s.price_change > 0 ? "var(--green)" : s.price_change < 0 ? "var(--red)" : "inherit" }}>
                  {s.price_change > 0 ? "+" : ""}{s.price_change}%
                </strong>
              </div>
              <div>
                <span style={{ color: "var(--text-secondary)" }}>置信 </span>
                <strong>{s.confidence}%</strong>
              </div>
            </div>

            {s.details.length > 0 && (
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 6 }}>
                {s.details[0]}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
