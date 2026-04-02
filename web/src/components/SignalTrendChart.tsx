"use client";

/**
 * Price chart with prominent buy/sell signal markers + click-to-expand.
 *
 * Mini mode (in card): Price line + colored signal flags
 * Expanded mode (modal): Full-width chart with detailed signal annotations
 */

import { useMemo, useState } from "react";
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
} from "recharts";
import type { SignalTrendPoint } from "@/lib/api";
import { shortDate } from "@/lib/format";

interface SignalTrendChartProps {
  data: SignalTrendPoint[];
  height?: number;
}

const DIR_LABELS: Record<string, string> = {
  strong_buy: "强买", buy: "买", hold: "观望", sell: "卖", strong_sell: "强卖",
};

/* ── Enrich data with signal outcomes ── */
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
      const futureIdx = Math.min(i + 5, data.length - 1);
      const futurePrice = data[futureIdx].close;
      nextReturn = ((futurePrice - d.close) / d.close) * 100;
      correct = isBuy ? nextReturn > 0 : nextReturn < 0;
    }

    return {
      ...d,
      signalMark: hasSignal ? d.close : null,
      isBuy,
      isSell,
      nextReturn,
      correct,
    };
  });
}

/* ── Signal flag on price chart ── */
function SignalFlag(props: { cx?: number; cy?: number; payload?: ChartPoint; large?: boolean }) {
  const { cx, cy, payload, large } = props;
  if (!cx || !cy || !payload || !payload.signalMark) return null;

  const color = payload.isBuy ? "#22c55e" : "#ef4444";
  const label = payload.isBuy ? "买" : "卖";
  const outcomeColor = payload.correct === true ? "#22c55e" : payload.correct === false ? "#ef4444" : "#64748b";
  const r = large ? 6 : 4;
  const flagW = large ? 22 : 16;
  const flagH = large ? 14 : 10;
  const fontSize = large ? 9 : 7;

  return (
    <g>
      {/* Vertical reference line */}
      <line x1={cx} y1={cy - (large ? 30 : 18)} x2={cx} y2={cy + (large ? 30 : 12)}
        stroke={color} strokeWidth={0.8} strokeDasharray="2 2" opacity={0.5} />

      {/* Outcome glow */}
      <circle cx={cx} cy={cy} r={r + 4} fill={outcomeColor} opacity={0.2} />

      {/* Main dot */}
      <circle cx={cx} cy={cy} r={r} fill={color} stroke="#0f172a" strokeWidth={1.5} />

      {/* Flag label */}
      <rect
        x={cx - flagW / 2} y={cy - flagH - r - 3}
        width={flagW} height={flagH} rx={3}
        fill={color}
      />
      <text
        x={cx} y={cy - r - 3 - flagH / 2 + 1}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={fontSize} fontWeight={800} fill="#fff"
      >
        {label}
      </text>

      {/* Outcome indicator (check/cross) below dot */}
      {payload.correct !== null && large && (
        <text
          x={cx} y={cy + r + 10}
          textAnchor="middle" fontSize={8} fontWeight={700}
          fill={outcomeColor}
        >
          {payload.correct ? "✓" : "✗"}
        </text>
      )}
    </g>
  );
}

/* ── Tooltip ── */
function ChartTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload: ChartPoint }>;
}) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  const hasSignal = d.signalMark !== null;
  const color = d.isBuy ? "#22c55e" : d.isSell ? "#ef4444" : "#64748b";

  return (
    <div style={{
      background: "rgba(15, 23, 42, 0.95)",
      border: `1px solid ${hasSignal ? color : "#334155"}`,
      borderRadius: 8, padding: "8px 12px",
      fontSize: "0.72rem", lineHeight: 1.6,
      backdropFilter: "blur(8px)",
      boxShadow: hasSignal ? `0 4px 16px ${color}33` : "none",
    }}>
      <div style={{ color: "#94a3b8", fontSize: "0.65rem" }}>{d.date}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
        <span style={{ fontWeight: 700, fontSize: "1rem" }}>¥{d.close.toFixed(3)}</span>
        {hasSignal && (
          <span style={{
            padding: "2px 8px", borderRadius: 4,
            fontSize: "0.65rem", fontWeight: 800,
            color: "#fff", background: color,
          }}>
            {DIR_LABELS[d.direction]} {d.score >= 0 ? "+" : ""}{d.score.toFixed(0)}
          </span>
        )}
      </div>
      {hasSignal && d.nextReturn !== null && (
        <div style={{ marginTop: 4, fontSize: "0.7rem", borderTop: "1px solid #334155", paddingTop: 4 }}>
          <span style={{ color: "#94a3b8" }}>5日后收益: </span>
          <span style={{
            fontWeight: 800, fontSize: "0.85rem",
            color: d.correct ? "#22c55e" : "#ef4444",
          }}>
            {d.nextReturn > 0 ? "+" : ""}{d.nextReturn.toFixed(2)}%
            {d.correct ? " ✓ 正确" : " ✗ 偏差"}
          </span>
        </div>
      )}
    </div>
  );
}

/* ── Shared chart renderer ── */
function PriceChart({
  data,
  enriched,
  priceHeight,
  barHeight,
  large,
}: {
  data: SignalTrendPoint[];
  enriched: ChartPoint[];
  priceHeight: number;
  barHeight: number;
  large?: boolean;
}) {
  return (
    <>
      <ResponsiveContainer width="100%" height={priceHeight}>
        <ComposedChart data={enriched} margin={{ top: large ? 28 : 20, right: 6, bottom: 0, left: 6 }}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.12} />
              <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
            </linearGradient>
          </defs>

          <XAxis dataKey="date" hide={!large} tickFormatter={shortDate}
            tick={large ? { fontSize: 10, fill: "#475569" } : undefined}
            axisLine={false} tickLine={false} />
          <YAxis hide={!large} domain={["auto", "auto"]}
            tick={large ? { fontSize: 10, fill: "#475569" } : undefined}
            tickFormatter={(v: number) => `¥${v.toFixed(2)}`}
            axisLine={false} tickLine={false} width={55} />

          {/* Buy/sell signal vertical reference lines */}
          {enriched.filter((d) => d.signalMark !== null).map((d, i) => (
            <ReferenceLine key={i} x={d.date} stroke={d.isBuy ? "#22c55e" : "#ef4444"}
              strokeWidth={0.5} strokeDasharray="3 3" strokeOpacity={0.3} />
          ))}

          <Area type="monotone" dataKey="close" stroke="#60a5fa" strokeWidth={large ? 2 : 1.5}
            fill="url(#priceGrad)" dot={false} isAnimationActive={false} />

          <Line type="monotone" dataKey="signalMark" stroke="none"
            dot={(props: Record<string, unknown>) => (
              <SignalFlag key={props.index as number}
                cx={props.cx as number} cy={props.cy as number}
                payload={props.payload as ChartPoint} large={large} />
            )}
            activeDot={false} isAnimationActive={false} connectNulls={false} />

          <Tooltip content={<ChartTooltip />}
            cursor={{ stroke: "#475569", strokeDasharray: "3 3" }} />
        </ComposedChart>
      </ResponsiveContainer>

      <ResponsiveContainer width="100%" height={barHeight}>
        <ComposedChart data={enriched} margin={{ top: 0, right: 6, bottom: 0, left: large ? 55 : 6 }}>
          <XAxis dataKey="date" tickFormatter={shortDate}
            tick={{ fontSize: large ? 10 : 8, fill: "#475569" }}
            axisLine={false} tickLine={false}
            interval={Math.max(0, Math.floor(data.length / (large ? 8 : 5)) - 1)} />
          <YAxis hide domain={["auto", "auto"]} />
          <Bar dataKey="score" isAnimationActive={false} barSize={large ? 5 : 3} radius={[1, 1, 0, 0]}>
            {enriched.map((d, i) => (
              <Cell key={i}
                fill={d.isBuy ? "#22c55e" : d.isSell ? "#ef4444" : "#334155"}
                fillOpacity={d.signalMark ? 0.9 : Math.min(1, 0.2 + Math.abs(d.score) / 40)} />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </>
  );
}

/* ── Main Component ── */
export default function SignalTrendChart({ data, height = 100 }: SignalTrendChartProps) {
  const [expanded, setExpanded] = useState(false);

  if (data.length === 0) return null;

  const enriched = useMemo(() => enrichData(data), [data]);
  const last = data[data.length - 1];

  const signalPoints = enriched.filter((d) => d.signalMark !== null);
  const buys = signalPoints.filter((d) => d.isBuy);
  const sells = signalPoints.filter((d) => d.isSell);
  const withOutcome = signalPoints.filter((d) => d.correct !== null);
  const correctCount = withOutcome.filter((d) => d.correct).length;
  const accuracy = withOutcome.length > 0 ? Math.round((correctCount / withOutcome.length) * 100) : null;

  const priceHeight = Math.round(height * 0.7);
  const barHeight = height - priceHeight;

  return (
    <>
      {/* Mini chart (in card) */}
      <div
        style={{ position: "relative", cursor: "pointer" }}
        onClick={(e) => { e.stopPropagation(); setExpanded(true); }}
        title="点击放大查看详细信号"
      >
        {/* Badge */}
        <div style={{
          position: "absolute", top: 0, right: 4, zIndex: 2,
          display: "flex", alignItems: "center", gap: 6,
        }}>
          {(buys.length > 0 || sells.length > 0) && (
            <span style={{ fontSize: "0.58rem", color: "#64748b" }}>
              {buys.length > 0 && <span style={{ color: "#4ade80" }}>{buys.length}买</span>}
              {buys.length > 0 && sells.length > 0 && " "}
              {sells.length > 0 && <span style={{ color: "#f87171" }}>{sells.length}卖</span>}
              {accuracy !== null && (
                <span style={{
                  marginLeft: 4, fontWeight: 700,
                  color: accuracy >= 55 ? "#4ade80" : accuracy >= 40 ? "#f59e0b" : "#f87171",
                }}>{accuracy}%准</span>
              )}
            </span>
          )}
          <span style={{
            fontWeight: 800, fontSize: "0.72rem", fontFamily: "monospace",
            color: "#60a5fa",
          }}>
            ¥{last.close.toFixed(3)}
          </span>
          <span style={{ fontSize: "0.55rem", color: "#475569" }}>🔍</span>
        </div>

        <PriceChart data={data} enriched={enriched}
          priceHeight={priceHeight} barHeight={barHeight} />
      </div>

      {/* Expanded modal */}
      {expanded && (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 9999,
            background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "1.5rem",
          }}
          onClick={() => setExpanded(false)}
        >
          <div
            style={{
              width: "100%", maxWidth: 1000,
              background: "var(--bg-secondary, #1e293b)",
              borderRadius: 16, padding: "1.25rem",
              border: "1px solid var(--border)",
              boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <div>
                <div style={{ fontSize: "1rem", fontWeight: 700 }}>
                  信号回验 · 60日价格走势
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 2 }}>
                  {buys.length > 0 && <span style={{ color: "#4ade80", marginRight: 12 }}>▲ 买入 {buys.length}次</span>}
                  {sells.length > 0 && <span style={{ color: "#f87171", marginRight: 12 }}>▼ 卖出 {sells.length}次</span>}
                  {accuracy !== null && (
                    <span style={{
                      fontWeight: 700,
                      color: accuracy >= 55 ? "#4ade80" : accuracy >= 40 ? "#f59e0b" : "#f87171",
                    }}>
                      准确率 {accuracy}% ({correctCount}/{withOutcome.length})
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => setExpanded(false)}
                style={{
                  background: "none", border: "1px solid var(--border)",
                  borderRadius: 8, padding: "6px 16px",
                  color: "var(--text-secondary)", fontSize: "0.8rem",
                  cursor: "pointer",
                }}
              >
                关闭
              </button>
            </div>

            {/* Large chart */}
            <PriceChart data={data} enriched={enriched}
              priceHeight={320} barHeight={60} large />

            {/* Signal history table */}
            {signalPoints.length > 0 && (
              <div style={{ marginTop: "0.75rem" }}>
                <div style={{ fontSize: "0.8rem", fontWeight: 700, marginBottom: 6, color: "var(--text-secondary)" }}>
                  信号记录
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 6 }}>
                  {signalPoints.map((d, i) => (
                    <div key={i} style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "6px 10px", borderRadius: 6,
                      background: "var(--bg-primary)",
                      border: `1px solid ${d.correct === true ? "#22c55e20" : d.correct === false ? "#ef444420" : "#33415540"}`,
                    }}>
                      <span style={{
                        padding: "2px 6px", borderRadius: 4, fontSize: "0.65rem",
                        fontWeight: 800, color: "#fff",
                        background: d.isBuy ? "#22c55e" : "#ef4444",
                      }}>
                        {d.isBuy ? "买" : "卖"}
                      </span>
                      <span style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>{d.date}</span>
                      <span className="mono" style={{ fontSize: "0.75rem", fontWeight: 600 }}>¥{d.close.toFixed(3)}</span>
                      {d.nextReturn !== null && (
                        <span style={{
                          marginLeft: "auto", fontSize: "0.7rem", fontWeight: 700,
                          color: d.correct ? "#22c55e" : "#ef4444",
                        }}>
                          {d.nextReturn > 0 ? "+" : ""}{d.nextReturn.toFixed(1)}%
                          {d.correct ? " ✓" : " ✗"}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Legend */}
            <div style={{ display: "flex", gap: "1.5rem", marginTop: "0.75rem", fontSize: "0.65rem", color: "var(--text-tertiary)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: "#22c55e" }} /> 买入信号
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: "#ef4444" }} /> 卖出信号
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", border: "2px solid #22c55e", background: "transparent" }} /> 绿光环=5日后验证正确
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", border: "2px solid #ef4444", background: "transparent" }} /> 红光环=5日后验证偏差
              </span>
              <span>分数条: 绿=买入信号强度 · 红=卖出 · 灰=观望</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
