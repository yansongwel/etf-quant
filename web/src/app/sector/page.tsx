"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { SectorData, SectorRotationResponse } from "@/lib/api";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
  PieChart,
  Pie,
} from "recharts";

const PHASE_STYLES: Record<string, { bg: string; border: string; icon: string; label: string; shortDesc: string; detail: string }> = {
  recovering: {
    bg: "rgba(34,197,94,0.08)", border: "#22c55e", icon: "🟢", label: "左侧布局",
    shortDesc: "跌速放缓，可提前小仓位埋伏",
    detail: "20日仍在下跌，但近5日跌幅收窄（动量加速转正）。属于左侧交易机会：短期可能还会小跌，但中期底部渐近。建议分2-3次小仓位（10-20%）试探建仓，等【交易信号】页出现买入信号后再加仓。",
  },
  leading: {
    bg: "rgba(59,130,246,0.08)", border: "#3b82f6", icon: "🔵", label: "领涨期",
    shortDesc: "趋势向上且加速中，顺势持有",
    detail: "20日动量为正且还在加速。这是最强势的阶段，已持有则继续持有或小幅加仓。未持有则可参考【交易信号】页的买入建议入场，但注意不要追高。",
  },
  weakening: {
    bg: "rgba(234,179,8,0.08)", border: "#eab308", icon: "🟡", label: "高位走弱",
    shortDesc: "涨势减速，准备止盈离场",
    detail: "20日动量为正但加速度转负（涨得越来越慢）。动量见顶信号，已持有应设好止盈位逐步减仓。不建议新开仓。",
  },
  lagging: {
    bg: "rgba(100,116,139,0.06)", border: "#64748b", icon: "⚪", label: "底部观望",
    shortDesc: "持续下跌且未见好转，暂不参与",
    detail: "20日动量为负且还在恶化。此阶段风险最大，耐心等待动量加速度转正（进入【左侧布局】阶段）后再考虑。",
  },
};

export default function SectorPage() {
  const [data, setData] = useState<SectorRotationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSector, setSelectedSector] = useState<SectorData | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.sectorRotation();
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const grouped: Record<string, SectorData[]> = {};
  if (data) {
    for (const s of data.sectors) {
      const phase = s.phase || "lagging";
      if (!grouped[phase]) grouped[phase] = [];
      grouped[phase].push(s);
    }
  }

  const phaseOrder = ["recovering", "leading", "weakening", "lagging"];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800 }}>板块轮动</h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 2 }}>
            中期趋势分析 · 判断各板块处于轮动周期的哪个位置 | {data?.count || 0} 个板块
            {data?.generated_at && (
              <span style={{ marginLeft: 8, fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                · {data.generated_at} CST
              </span>
            )}
          </p>
        </div>
        <button className="btn btn-primary" onClick={refresh} disabled={loading}>
          {loading ? "加载中..." : "刷新数据"}
        </button>
      </div>

      {error && <ErrorBanner message={`板块数据加载失败: ${error}`} onRetry={refresh} />}
      {loading && !data && <LoadingSkeleton rows={4} height={80} />}

      {/* Phase legend with explanations */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1.5rem" }}>
        {phaseOrder.map((phase) => {
          const style = PHASE_STYLES[phase];
          const count = grouped[phase]?.length || 0;
          return (
            <div key={phase} style={{
              padding: "0.75rem 1rem", borderRadius: 8,
              background: style.bg, border: `1px solid ${style.border}40`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span style={{ fontSize: "1.1rem" }}>{style.icon}</span>
                <span style={{ fontSize: "0.9rem", fontWeight: 700, color: style.border }}>{style.label}</span>
                <span style={{ marginLeft: "auto", fontSize: "1.2rem", fontWeight: 800, color: style.border }}>{count}</span>
              </div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                {style.shortDesc}
              </div>
            </div>
          );
        })}
      </div>

      {/* ─── Rotation Cycle Ring ─── */}
      {data && data.sectors.length > 0 && (() => {
        const phaseColor: Record<string, string> = {
          recovering: "#22c55e", leading: "#3b82f6",
          weakening: "#eab308", lagging: "#64748b",
        };
        const ringData = phaseOrder.map((phase) => ({
          name: PHASE_STYLES[phase]?.label || phase,
          value: grouped[phase]?.length || 0,
          phase,
          sectors: (grouped[phase] || []).map((s) => s.sector_name).join("、"),
        })).filter((d) => d.value > 0);
        const total = data.sectors.length;

        return (
          <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "1rem", marginBottom: "1.25rem" }}>
            {/* Ring */}
            <div className="card" style={{ padding: "0.75rem", display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, marginBottom: 4, color: "var(--text-secondary)" }}>
                轮动周期分布
              </div>
              <div style={{ position: "relative", width: 150, height: 150 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={ringData}
                      cx="50%"
                      cy="50%"
                      innerRadius={42}
                      outerRadius={65}
                      dataKey="value"
                      startAngle={90}
                      endAngle={-270}
                      stroke="none"
                    >
                      {ringData.map((d) => (
                        <Cell key={d.phase} fill={phaseColor[d.phase] || "#64748b"} />
                      ))}
                    </Pie>
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.[0]) return null;
                        const d = payload[0].payload as typeof ringData[0];
                        return (
                          <div style={{
                            background: "rgba(15,23,42,0.95)", borderRadius: 8,
                            padding: "8px 12px", fontSize: "0.72rem",
                            border: `1px solid ${phaseColor[d.phase]}44`,
                          }}>
                            <div style={{ fontWeight: 700, color: phaseColor[d.phase] }}>{d.name} ({d.value})</div>
                            <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>{d.sectors}</div>
                          </div>
                        );
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                {/* Center label */}
                <div style={{
                  position: "absolute", top: "50%", left: "50%",
                  transform: "translate(-50%, -50%)", textAlign: "center",
                }}>
                  <div style={{ fontSize: "1.4rem", fontWeight: 800 }}>{total}</div>
                  <div style={{ fontSize: "0.6rem", color: "var(--text-tertiary)" }}>板块</div>
                </div>
              </div>
              {/* Ring legend */}
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center", marginTop: 4 }}>
                {ringData.map((d) => (
                  <span key={d.phase} style={{ display: "flex", alignItems: "center", gap: 3, fontSize: "0.6rem", color: "var(--text-secondary)" }}>
                    <span style={{ width: 6, height: 6, borderRadius: 2, background: phaseColor[d.phase] }} />
                    {d.name} {d.value}
                  </span>
                ))}
              </div>
            </div>

            {/* Phase flow description */}
            <div className="card" style={{ padding: "0.75rem", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, marginBottom: 8, color: "var(--text-secondary)" }}>
                轮动周期说明
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap", fontSize: "0.75rem" }}>
                {[
                  { phase: "recovering", arrow: "→" },
                  { phase: "leading", arrow: "→" },
                  { phase: "weakening", arrow: "→" },
                  { phase: "lagging", arrow: "→" },
                ].map((item, i) => {
                  const ps = PHASE_STYLES[item.phase];
                  const count = grouped[item.phase]?.length || 0;
                  return (
                    <span key={item.phase} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <span style={{
                        padding: "4px 10px", borderRadius: 6,
                        background: `${phaseColor[item.phase]}20`,
                        color: phaseColor[item.phase],
                        fontWeight: 700, fontSize: "0.8rem",
                      }}>
                        {ps?.icon} {ps?.label} ({count})
                      </span>
                      {i < 3 && <span style={{ color: "var(--text-tertiary)", fontSize: "1rem" }}>→</span>}
                    </span>
                  );
                })}
              </div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginTop: 8, lineHeight: 1.5 }}>
                板块轮动遵循：底部观望 → 左侧布局（跌速放缓）→ 领涨期（趋势确认）→ 高位走弱（准备离场）→ 底部观望。
                当前 {grouped.recovering?.length || 0} 个板块进入左侧布局阶段，是提前埋伏的窗口。
              </div>
            </div>
          </div>
        );
      })()}

      {/* ─── Momentum Bar Chart ─── */}
      {data && data.sectors.length > 0 && (() => {
        const chartData = [...data.sectors]
          .sort((a, b) => b.momentum_20d - a.momentum_20d)
          .map((s) => ({
            name: s.sector_name,
            momentum: s.momentum_20d,
            mom5d: s.momentum_5d,
            phase: s.phase,
            rsi: s.rsi,
            best: s.best_etf_name,
          }));
        const phaseColor: Record<string, string> = {
          recovering: "#22c55e",
          leading: "#3b82f6",
          weakening: "#eab308",
          lagging: "#64748b",
        };
        return (
          <div className="card" style={{ padding: "1rem", marginBottom: "1.25rem" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: "0.5rem" }}>
              板块20日动量排名
            </div>
            <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 36)}>
              <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 20, bottom: 0, left: 75 }}>
                <XAxis type="number" tick={{ fontSize: 10, fill: "#64748b" }} tickFormatter={(v: number) => `${v}%`} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11, fill: "#94a3b8", fontWeight: 600 }}
                  width={70}
                />
                <ReferenceLine x={0} stroke="#334155" strokeWidth={1} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.[0]) return null;
                    const d = payload[0].payload as typeof chartData[0];
                    const c = phaseColor[d.phase] || "#64748b";
                    return (
                      <div style={{
                        background: "rgba(15,23,42,0.95)", borderRadius: 8,
                        padding: "8px 12px", fontSize: "0.75rem", border: `1px solid ${c}44`,
                      }}>
                        <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.name}</div>
                        <div>20日动量: <strong style={{ color: d.momentum >= 0 ? "#4ade80" : "#f87171" }}>
                          {d.momentum > 0 ? "+" : ""}{d.momentum.toFixed(1)}%
                        </strong></div>
                        <div>5日动量: <strong style={{ color: d.mom5d >= 0 ? "#4ade80" : "#f87171" }}>
                          {d.mom5d > 0 ? "+" : ""}{d.mom5d.toFixed(1)}%
                        </strong></div>
                        <div>RSI: <strong>{d.rsi.toFixed(0)}</strong> · 推荐: <strong>{d.best}</strong></div>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="momentum" radius={[0, 4, 4, 0]} barSize={20}>
                  {chartData.map((d, i) => (
                    <Cell key={i} fill={phaseColor[d.phase] || "#64748b"} fillOpacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div style={{ display: "flex", gap: "1rem", justifyContent: "center", marginTop: 6, fontSize: "0.6rem", color: "var(--text-tertiary)" }}>
              {Object.entries(phaseColor).map(([phase, color]) => (
                <span key={phase} style={{ display: "flex", alignItems: "center", gap: 3 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
                  {PHASE_STYLES[phase]?.label || phase}
                </span>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Sector cards by phase */}
      {phaseOrder.map((phase) => {
        const sectors = grouped[phase];
        if (!sectors || sectors.length === 0) return null;
        const style = PHASE_STYLES[phase];

        return (
          <div key={phase} style={{ marginBottom: "1.5rem" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.4rem", color: style.border }}>
              {style.icon} {style.label}（{sectors.length}）
            </h3>
            <div style={{
              fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.5,
              marginBottom: "0.75rem", padding: "0.5rem 0.75rem",
              background: `${style.border}08`, borderRadius: 6,
              borderLeft: `3px solid ${style.border}`,
            }}>
              {style.detail}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "0.75rem" }}>
              {sectors.map((s) => (
                <div
                  key={s.sector_name}
                  className="card"
                  onClick={() => setSelectedSector(selectedSector?.sector_name === s.sector_name ? null : s)}
                  style={{
                    cursor: "pointer",
                    borderColor: selectedSector?.sector_name === s.sector_name ? style.border : undefined,
                    borderWidth: selectedSector?.sector_name === s.sector_name ? 2 : 1,
                    background: style.bg,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontSize: "1.1rem", fontWeight: 700 }}>{s.sector_name}</span>
                    <span style={{ fontSize: "0.75rem", padding: "2px 8px", borderRadius: 4, background: `${style.border}20`, color: style.border, fontWeight: 600 }}>
                      {s.phase_label}
                    </span>
                  </div>

                  {/* Key metrics */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 6, marginBottom: 8 }}>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>20日动量</div>
                      <div style={{ fontWeight: 700, fontSize: "0.9rem", color: s.momentum_20d > 0 ? "var(--green)" : "var(--red)" }}>
                        {s.momentum_20d > 0 ? "+" : ""}{s.momentum_20d}%
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>5日动量</div>
                      <div style={{ fontWeight: 700, fontSize: "0.9rem", color: s.momentum_5d > 0 ? "var(--green)" : "var(--red)" }}>
                        {s.momentum_5d > 0 ? "+" : ""}{s.momentum_5d}%
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>RSI</div>
                      <div style={{ fontWeight: 700, fontSize: "0.9rem", color: s.rsi > 70 ? "var(--red)" : s.rsi < 30 ? "var(--green)" : "var(--text-primary)" }}>
                        {s.rsi.toFixed(1)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>波动率</div>
                      <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{s.volatility}%</div>
                    </div>
                  </div>

                  {/* Best ETF */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", background: "var(--bg-primary)", borderRadius: 6 }}>
                    <div>
                      <span style={{ fontFamily: "monospace", fontWeight: 700 }}>{s.best_etf}</span>
                      <span style={{ marginLeft: 6, fontSize: "0.8rem", color: "var(--text-secondary)" }}>{s.best_etf_name}</span>
                    </div>
                    <span style={{ fontSize: "0.75rem", color: style.border, fontWeight: 600 }}>
                      配置 {s.allocation_pct}%
                    </span>
                  </div>

                  {/* Action */}
                  <div style={{ fontSize: "0.8rem", marginTop: 8, color: "var(--text-secondary)" }}>
                    {s.action}
                  </div>

                  {/* Expanded detail */}
                  {selectedSector?.sector_name === s.sector_name && (
                    <div style={{ marginTop: 12, padding: "10px", background: "var(--bg-primary)", borderRadius: 8 }}>
                      <div style={{ fontSize: "0.8rem", fontWeight: 600, marginBottom: 6 }}>板块详情</div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: "0.8rem" }}>
                        <div>动量加速度: <strong style={{ color: s.momentum_acceleration > 0 ? "var(--green)" : "var(--red)" }}>
                          {s.momentum_acceleration > 0 ? "+" : ""}{s.momentum_acceleration.toFixed(2)}
                        </strong></div>
                        <div>MA比率: <strong>{s.ma_ratio.toFixed(4)}</strong></div>
                        <div>评分: <strong>{s.score.toFixed(2)}</strong></div>
                        <div>风险等级: <strong>{s.risk_level}</strong></div>
                      </div>
                      <div style={{ fontSize: "0.75rem", marginTop: 8, color: "var(--text-secondary)" }}>
                        ETF池: {s.etf_symbols.join(", ")}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* Rotation clock visualization */}
      {data && data.sectors.length > 0 && (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "1rem" }}>轮动一览表</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>板块</th>
                <th>阶段</th>
                <th>推荐ETF</th>
                <th>20日动量</th>
                <th>5日动量</th>
                <th>加速度</th>
                <th>RSI</th>
                <th>波动率</th>
                <th>评分</th>
                <th>配置比例</th>
                <th>风险</th>
              </tr>
            </thead>
            <tbody>
              {data.sectors
                .sort((a, b) => b.score - a.score)
                .map((s) => {
                  const ps = PHASE_STYLES[s.phase] || PHASE_STYLES.lagging;
                  return (
                    <tr key={s.sector_name}>
                      <td style={{ fontWeight: 700 }}>{s.sector_name}</td>
                      <td>
                        <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.75rem", background: `${ps.border}20`, color: ps.border, fontWeight: 600 }}>
                          {ps.icon} {ps.label}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontFamily: "monospace", fontWeight: 600 }}>{s.best_etf}</span>
                        <span style={{ marginLeft: 4, fontSize: "0.75rem", color: "var(--text-secondary)" }}>{s.best_etf_name}</span>
                      </td>
                      <td style={{ color: s.momentum_20d > 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                        {s.momentum_20d > 0 ? "+" : ""}{s.momentum_20d}%
                      </td>
                      <td style={{ color: s.momentum_5d > 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                        {s.momentum_5d > 0 ? "+" : ""}{s.momentum_5d}%
                      </td>
                      <td style={{ color: s.momentum_acceleration > 0 ? "var(--green)" : "var(--red)" }}>
                        {s.momentum_acceleration > 0 ? "+" : ""}{s.momentum_acceleration.toFixed(1)}
                      </td>
                      <td style={{ color: s.rsi > 70 ? "var(--red)" : s.rsi < 30 ? "var(--green)" : "inherit" }}>
                        {s.rsi.toFixed(1)}
                      </td>
                      <td>{s.volatility}%</td>
                      <td style={{ fontWeight: 700 }}>{s.score.toFixed(2)}</td>
                      <td style={{ fontWeight: 600 }}>{s.allocation_pct}%</td>
                      <td style={{ fontSize: "0.75rem" }}>{s.risk_level}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
