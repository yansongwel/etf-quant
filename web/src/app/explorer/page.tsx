"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { SectorGroup, SignalTrendPoint } from "@/lib/api";
import { shortDate } from "@/lib/format";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import {
  ComposedChart,
  Area,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
  CartesianGrid,
} from "recharts";

/* ─── Constants ─── */

const PHASE_COLORS: Record<string, string> = {
  recovering: "#22c55e",
  leading: "#3b82f6",
  weakening: "#eab308",
  lagging: "#64748b",
};

const PERIOD_OPTIONS = [
  { label: "1个月", days: 20 },
  { label: "3个月", days: 60 },
  { label: "6个月", days: 125 },
  { label: "1年", days: 250 },
];

/* ─── Signal enrichment (same logic as SignalTrendChart) ─── */

interface ChartPoint extends SignalTrendPoint {
  signalMark: number | null;
  isBuy: boolean;
  isSell: boolean;
  nextReturn: number | null;
  correct: boolean | null;
}

function enrichData(data: SignalTrendPoint[]): ChartPoint[] {
  return data.map((d, i) => {
    const isBuy = d.direction === "buy" || d.direction === "strong_buy";
    const isSell = d.direction === "sell" || d.direction === "strong_sell";
    const hasSignal = isBuy || isSell;
    let nextReturn: number | null = null;
    let correct: boolean | null = null;
    if (hasSignal && i + 3 <= data.length - 1) {
      const fi = Math.min(i + 5, data.length - 1);
      nextReturn = ((data[fi].close - d.close) / d.close) * 100;
      correct = isBuy ? nextReturn > 0 : nextReturn < 0;
    }
    return { ...d, signalMark: hasSignal ? d.close : null, isBuy, isSell, nextReturn, correct };
  });
}

/* ─── Signal flag on chart ─── */

function SignalFlag(props: { cx?: number; cy?: number; payload?: ChartPoint }) {
  const { cx, cy, payload } = props;
  if (!cx || !cy || !payload || !payload.signalMark) return null;
  const color = payload.isBuy ? "#22c55e" : "#ef4444";
  const label = payload.isBuy ? "买" : "卖";
  const outcomeColor = payload.correct === true ? "#22c55e" : payload.correct === false ? "#ef4444" : "#64748b";

  return (
    <g>
      <line x1={cx} y1={cy - 35} x2={cx} y2={cy + 35}
        stroke={color} strokeWidth={0.7} strokeDasharray="3 3" opacity={0.4} />
      <circle cx={cx} cy={cy} r={10} fill={outcomeColor} opacity={0.15} />
      <circle cx={cx} cy={cy} r={5} fill={color} stroke="#0f172a" strokeWidth={2} />
      <rect x={cx - 12} y={cy - 24} width={24} height={15} rx={4} fill={color} />
      <text x={cx} y={cy - 16} textAnchor="middle" dominantBaseline="middle"
        fontSize={10} fontWeight={800} fill="#fff">{label}</text>
      {payload.correct !== null && (
        <text x={cx} y={cy + 16} textAnchor="middle" fontSize={10} fontWeight={700} fill={outcomeColor}>
          {payload.correct ? "✓" : "✗"}
        </text>
      )}
    </g>
  );
}

/* ─── Tooltip ─── */

function ExplorerTooltip({ active, payload }: {
  active?: boolean; payload?: Array<{ payload: ChartPoint }>;
}) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  const hasSignal = d.signalMark !== null;
  const color = d.isBuy ? "#22c55e" : d.isSell ? "#ef4444" : "#64748b";
  return (
    <div style={{
      background: "rgba(15,23,42,0.95)", border: `1px solid ${hasSignal ? color : "#334155"}`,
      borderRadius: 10, padding: "10px 14px", fontSize: "0.78rem", lineHeight: 1.7,
      backdropFilter: "blur(8px)", boxShadow: hasSignal ? `0 4px 20px ${color}33` : "none",
    }}>
      <div style={{ color: "#94a3b8", fontSize: "0.7rem" }}>{d.date}</div>
      <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>¥{d.close.toFixed(3)}</div>
      {hasSignal && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
            <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 800, color: "#fff", background: color }}>
              {d.isBuy ? "买入" : "卖出"} 信号
            </span>
            <span style={{ fontFamily: "monospace", fontWeight: 600 }}>
              分数: {d.score >= 0 ? "+" : ""}{d.score.toFixed(1)}
            </span>
          </div>
          {d.nextReturn !== null && (
            <div style={{ marginTop: 4, padding: "4px 0", borderTop: "1px solid #334155" }}>
              5日后收益:
              <strong style={{ marginLeft: 6, fontSize: "0.95rem", color: d.correct ? "#22c55e" : "#ef4444" }}>
                {d.nextReturn > 0 ? "+" : ""}{d.nextReturn.toFixed(2)}%
                {d.correct ? " ✓ 正确" : " ✗ 偏差"}
              </strong>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─── Inner component using searchParams ─── */

function ExplorerInner() {
  const searchParams = useSearchParams();
  const initialSymbol = searchParams.get("symbol") || "";

  const [groups, setGroups] = useState<SectorGroup[]>([]);
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState(initialSymbol);
  const [selectedName, setSelectedName] = useState("");
  const [period, setPeriod] = useState(60);
  const [trendData, setTrendData] = useState<SignalTrendPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [error, setError] = useState("");

  // Load sector groups
  useEffect(() => {
    setGroupsLoading(true);
    api.sectorGroups()
      .then((r) => {
        setGroups(r.groups);
        // Auto-select sector for initial symbol
        if (initialSymbol) {
          for (const g of r.groups) {
            const found = g.etfs.find((e) => e.symbol === initialSymbol);
            if (found) {
              setSelectedSector(g.sector);
              setSelectedName(found.name);
              break;
            }
          }
        }
      })
      .catch(() => {})
      .finally(() => setGroupsLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load trend data when symbol or period changes
  const loadTrend = useCallback(async () => {
    if (!selectedSymbol) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.signalTrend(selectedSymbol, period);
      setTrendData(res.trend);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
      setTrendData([]);
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol, period]);

  useEffect(() => {
    loadTrend();
  }, [loadTrend]);

  const selectETF = (symbol: string, name: string) => {
    setSelectedSymbol(symbol);
    setSelectedName(name);
    // Update URL without navigation
    window.history.replaceState(null, "", `/explorer?symbol=${symbol}`);
  };

  const enriched = enrichData(trendData);
  const signalPoints = enriched.filter((d) => d.signalMark !== null);
  const buys = signalPoints.filter((d) => d.isBuy);
  const sells = signalPoints.filter((d) => d.isSell);
  const withOutcome = signalPoints.filter((d) => d.correct !== null);
  const correctCount = withOutcome.filter((d) => d.correct).length;
  const accuracy = withOutcome.length > 0 ? Math.round((correctCount / withOutcome.length) * 100) : null;

  const activeSector = groups.find((g) => g.sector === selectedSector);

  return (
    <div className="fade-in">
      {/* Header */}
      <div style={{ marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "1.5rem", fontWeight: 800 }}>信号回验</h2>
        <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 2 }}>
          选择板块和ETF，查看历史买卖信号在价格图上的表现，验证信号准确性
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: "1rem", minHeight: "70vh" }}>
        {/* ── Left: Sector + ETF Navigator ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {groupsLoading && <LoadingSkeleton rows={6} height={36} />}
          {groups.map((g) => {
            const isOpen = selectedSector === g.sector;
            const phaseColor = PHASE_COLORS[g.phase] || "#64748b";
            return (
              <div key={g.sector}>
                {/* Sector header */}
                <button
                  onClick={() => setSelectedSector(isOpen ? null : g.sector)}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", gap: 8,
                    padding: "8px 12px", borderRadius: 8, border: "none",
                    background: isOpen ? `${phaseColor}15` : "var(--bg-secondary)",
                    cursor: "pointer", transition: "all 0.15s",
                  }}
                >
                  <span style={{ fontSize: "0.65rem", color: phaseColor, fontWeight: 700, minWidth: 40 }}>
                    {g.phase_label.split(" ")[0]}
                  </span>
                  <span style={{ fontWeight: 700, fontSize: "0.85rem", color: isOpen ? "var(--text-primary)" : "var(--text-secondary)" }}>
                    {g.sector}
                  </span>
                  <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "var(--text-tertiary)" }}>
                    {g.etfs.length}
                  </span>
                  <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", transform: isOpen ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}>
                    ▶
                  </span>
                </button>

                {/* ETF list */}
                {isOpen && (
                  <div style={{ padding: "4px 0 4px 12px" }}>
                    {g.etfs.map((etf) => {
                      const active = selectedSymbol === etf.symbol;
                      return (
                        <button
                          key={etf.symbol}
                          onClick={() => selectETF(etf.symbol, etf.name)}
                          style={{
                            width: "100%", display: "flex", alignItems: "center", gap: 6,
                            padding: "6px 10px", borderRadius: 6, border: "none",
                            background: active ? "var(--accent-glow)" : "transparent",
                            cursor: "pointer", transition: "all 0.12s",
                            borderLeft: active ? `3px solid var(--accent)` : "3px solid transparent",
                          }}
                        >
                          <span style={{
                            fontFamily: "monospace", fontSize: "0.75rem", fontWeight: 600,
                            color: active ? "var(--accent)" : "var(--text-tertiary)",
                          }}>{etf.symbol}</span>
                          <span style={{
                            fontSize: "0.78rem",
                            color: active ? "var(--text-primary)" : "var(--text-secondary)",
                            fontWeight: active ? 600 : 400,
                          }}>{etf.name}</span>
                          {etf.symbol === g.best_etf && (
                            <span style={{ marginLeft: "auto", fontSize: "0.55rem", padding: "1px 4px", borderRadius: 3, background: `${phaseColor}20`, color: phaseColor, fontWeight: 600 }}>
                              推荐
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Right: Chart Area ── */}
        <div>
          {!selectedSymbol && (
            <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 400, color: "var(--text-tertiary)" }}>
              ← 选择左侧板块和 ETF 查看信号回验
            </div>
          )}

          {selectedSymbol && (
            <>
              {/* ETF header + period selector */}
              <div className="card" style={{ marginBottom: "0.75rem", padding: "0.75rem 1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <span style={{ fontSize: "1.2rem", fontWeight: 800 }}>{selectedName || selectedSymbol}</span>
                    <span style={{ marginLeft: 8, fontFamily: "monospace", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>{selectedSymbol}</span>
                    {trendData.length > 0 && (
                      <span style={{ marginLeft: 12, fontSize: "1.1rem", fontWeight: 700, fontFamily: "monospace", color: "#60a5fa" }}>
                        ¥{trendData[trendData.length - 1].close.toFixed(3)}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: "0.3rem", alignItems: "center" }}>
                    {PERIOD_OPTIONS.map((p) => (
                      <button key={p.days} onClick={() => setPeriod(p.days)}
                        style={{
                          padding: "5px 12px", borderRadius: 6, fontSize: "0.78rem",
                          border: `1.5px solid ${period === p.days ? "var(--accent)" : "var(--border)"}`,
                          background: period === p.days ? "var(--accent-glow)" : "transparent",
                          color: period === p.days ? "var(--accent)" : "var(--text-secondary)",
                          fontWeight: period === p.days ? 700 : 500, cursor: "pointer",
                        }}
                      >{p.label}</button>
                    ))}
                  </div>
                </div>

                {/* Signal stats */}
                {signalPoints.length > 0 && (
                  <div style={{ display: "flex", gap: "1.5rem", marginTop: 8, fontSize: "0.78rem" }}>
                    {buys.length > 0 && (
                      <span style={{ color: "#4ade80" }}>
                        ▲ 买入 {buys.length}次
                        {buys.filter((d) => d.correct !== null).length > 0 && (
                          <span style={{ marginLeft: 4, fontWeight: 700 }}>
                            ({buys.filter((d) => d.correct).length}/{buys.filter((d) => d.correct !== null).length} 正确)
                          </span>
                        )}
                      </span>
                    )}
                    {sells.length > 0 && (
                      <span style={{ color: "#f87171" }}>
                        ▼ 卖出 {sells.length}次
                        {sells.filter((d) => d.correct !== null).length > 0 && (
                          <span style={{ marginLeft: 4, fontWeight: 700 }}>
                            ({sells.filter((d) => d.correct).length}/{sells.filter((d) => d.correct !== null).length} 正确)
                          </span>
                        )}
                      </span>
                    )}
                    {accuracy !== null && (
                      <span style={{
                        fontWeight: 800,
                        color: accuracy >= 55 ? "#22c55e" : accuracy >= 40 ? "#f59e0b" : "#ef4444",
                      }}>
                        综合准确率 {accuracy}%
                      </span>
                    )}
                  </div>
                )}
              </div>

              {error && <ErrorBanner message={error} onRetry={loadTrend} />}
              {loading && <LoadingSkeleton rows={1} height={350} />}

              {/* ── Main Price Chart ── */}
              {!loading && trendData.length > 0 && (
                <div className="card" style={{ padding: "0.75rem", marginBottom: "0.75rem" }}>
                  <ResponsiveContainer width="100%" height={380}>
                    <ComposedChart data={enriched} margin={{ top: 30, right: 10, bottom: 5, left: 10 }}>
                      <defs>
                        <linearGradient id="explorerPriceGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.12} />
                          <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                      <XAxis dataKey="date" tickFormatter={shortDate}
                        tick={{ fontSize: 10, fill: "#475569" }} axisLine={false} tickLine={false} />
                      <YAxis domain={["auto", "auto"]}
                        tick={{ fontSize: 10, fill: "#475569" }}
                        tickFormatter={(v: number) => `¥${v.toFixed(2)}`}
                        axisLine={false} tickLine={false} width={60} />

                      {enriched.filter((d) => d.signalMark !== null).map((d, i) => (
                        <ReferenceLine key={i} x={d.date}
                          stroke={d.isBuy ? "#22c55e" : "#ef4444"}
                          strokeWidth={0.7} strokeDasharray="4 3" strokeOpacity={0.3} />
                      ))}

                      <Area type="monotone" dataKey="close" stroke="#60a5fa" strokeWidth={2}
                        fill="url(#explorerPriceGrad)" dot={false} isAnimationActive={false} />
                      <Line type="monotone" dataKey="signalMark" stroke="none"
                        dot={(props: Record<string, unknown>) => (
                          <SignalFlag key={props.index as number}
                            cx={props.cx as number} cy={props.cy as number}
                            payload={props.payload as ChartPoint} />
                        )}
                        activeDot={false} isAnimationActive={false} connectNulls={false} />
                      <Tooltip content={<ExplorerTooltip />}
                        cursor={{ stroke: "#475569", strokeDasharray: "3 3" }} />
                    </ComposedChart>
                  </ResponsiveContainer>

                  {/* Mini score bar */}
                  <ResponsiveContainer width="100%" height={50}>
                    <ComposedChart data={enriched} margin={{ top: 0, right: 10, bottom: 0, left: 60 }}>
                      <XAxis dataKey="date" hide />
                      <YAxis hide domain={["auto", "auto"]} />
                      <Bar dataKey="score" isAnimationActive={false} barSize={4} radius={[1, 1, 0, 0]}>
                        {enriched.map((d, i) => (
                          <Cell key={i}
                            fill={d.isBuy ? "#22c55e" : d.isSell ? "#ef4444" : "#334155"}
                            fillOpacity={d.signalMark ? 0.9 : 0.3} />
                        ))}
                      </Bar>
                    </ComposedChart>
                  </ResponsiveContainer>

                  {/* Legend */}
                  <div style={{ display: "flex", gap: "1.5rem", justifyContent: "center", marginTop: 6, fontSize: "0.65rem", color: "var(--text-tertiary)" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <span style={{ display: "inline-block", width: 14, height: 10, borderRadius: 3, background: "#22c55e" }} /> 买入信号
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <span style={{ display: "inline-block", width: 14, height: 10, borderRadius: 3, background: "#ef4444" }} /> 卖出信号
                    </span>
                    <span>绿色光环/✓ = 5日后验证正确</span>
                    <span>红色光环/✗ = 5日后验证偏差</span>
                    <span>底部条形图 = 信号分数强度</span>
                  </div>
                </div>
              )}

              {/* ── Signal Record Table ── */}
              {signalPoints.length > 0 && (
                <div className="card" style={{ padding: "0.75rem" }}>
                  <div style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: 8 }}>
                    信号记录 ({signalPoints.length}条)
                  </div>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        <th style={{ textAlign: "left", padding: "6px 8px", color: "var(--text-secondary)", fontWeight: 600 }}>日期</th>
                        <th style={{ textAlign: "center", padding: "6px 8px", color: "var(--text-secondary)", fontWeight: 600 }}>信号</th>
                        <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-secondary)", fontWeight: 600 }}>分数</th>
                        <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-secondary)", fontWeight: 600 }}>价格</th>
                        <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-secondary)", fontWeight: 600 }}>5日收益</th>
                        <th style={{ textAlign: "center", padding: "6px 8px", color: "var(--text-secondary)", fontWeight: 600 }}>结果</th>
                      </tr>
                    </thead>
                    <tbody>
                      {signalPoints.map((d, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "8px", fontFamily: "monospace" }}>{d.date}</td>
                          <td style={{ padding: "8px", textAlign: "center" }}>
                            <span style={{
                              padding: "2px 10px", borderRadius: 4, fontSize: "0.72rem",
                              fontWeight: 800, color: "#fff",
                              background: d.isBuy ? "#22c55e" : "#ef4444",
                            }}>
                              {d.isBuy ? "买入" : "卖出"}
                            </span>
                          </td>
                          <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace", fontWeight: 600 }}>
                            {d.score >= 0 ? "+" : ""}{d.score.toFixed(1)}
                          </td>
                          <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace" }}>
                            ¥{d.close.toFixed(3)}
                          </td>
                          <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: d.nextReturn !== null ? (d.nextReturn > 0 ? "#4ade80" : "#f87171") : "var(--text-tertiary)" }}>
                            {d.nextReturn !== null ? `${d.nextReturn > 0 ? "+" : ""}${d.nextReturn.toFixed(2)}%` : "—"}
                          </td>
                          <td style={{ padding: "8px", textAlign: "center", fontWeight: 700, fontSize: "0.85rem" }}>
                            {d.correct === true && <span style={{ color: "#22c55e" }}>✓ 正确</span>}
                            {d.correct === false && <span style={{ color: "#ef4444" }}>✗ 偏差</span>}
                            {d.correct === null && <span style={{ color: "var(--text-tertiary)" }}>待验证</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Page wrapper with Suspense for useSearchParams ─── */

export default function ExplorerPage() {
  return (
    <Suspense fallback={<LoadingSkeleton rows={5} height={80} />}>
      <ExplorerInner />
    </Suspense>
  );
}
