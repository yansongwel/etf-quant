"use client";

/**
 * ETF Signal Heatmap — Professional quant-style tile grid.
 * Each ETF is a colored tile: green=buy, red=sell, gray=hold.
 * Tile size proportional to abs(score). Hover shows details.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";

interface Signal {
  symbol: string;
  name?: string;
  direction: string;
  score: number;
  current_price: number;
}

interface SignalHeatmapProps {
  signals: Signal[];
}

const DIR_BG: Record<string, { bg: string; border: string; text: string }> = {
  strong_buy: { bg: "rgba(34, 197, 94, 0.35)", border: "#22c55e", text: "#4ade80" },
  buy: { bg: "rgba(34, 197, 94, 0.18)", border: "#22c55e80", text: "#4ade80" },
  hold: { bg: "rgba(100, 116, 139, 0.10)", border: "#33415540", text: "#94a3b8" },
  sell: { bg: "rgba(239, 68, 68, 0.18)", border: "#ef444480", text: "#f87171" },
  strong_sell: { bg: "rgba(239, 68, 68, 0.35)", border: "#ef4444", text: "#ef4444" },
};

const DIR_LABELS: Record<string, string> = {
  strong_buy: "强买",
  buy: "买入",
  hold: "观望",
  sell: "卖出",
  strong_sell: "强卖",
};

export default function SignalHeatmap({ signals }: SignalHeatmapProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const router = useRouter();

  if (signals.length === 0) return null;

  // Sort: buy signals first (highest score), then hold, then sell
  const sorted = [...signals].sort((a, b) => b.score - a.score);

  return (
    <div>
      <div style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 4,
      }}>
        {sorted.map((s) => {
          const style = DIR_BG[s.direction] || DIR_BG.hold;
          const isHovered = hovered === s.symbol;
          const absScore = Math.abs(s.score);
          // Tile opacity based on score strength
          const intensity = Math.min(1, 0.5 + absScore / 40);

          return (
            <div
              key={s.symbol}
              onMouseEnter={() => setHovered(s.symbol)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => router.push(`/explorer?symbol=${s.symbol}`)}
              style={{
                position: "relative",
                minWidth: 72,
                flex: "1 0 72px",
                maxWidth: 120,
                padding: "6px 8px",
                borderRadius: 6,
                background: style.bg,
                border: `1px solid ${isHovered ? style.border : "transparent"}`,
                opacity: intensity,
                cursor: "pointer",
                transition: "all 0.12s",
                transform: isHovered ? "scale(1.05)" : "scale(1)",
                zIndex: isHovered ? 2 : 1,
              }}
            >
              {/* Name + Score */}
              <div style={{
                fontSize: "0.68rem",
                fontWeight: 700,
                color: style.text,
                lineHeight: 1.3,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}>
                {s.name || s.symbol}
              </div>
              <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginTop: 2,
              }}>
                <span style={{
                  fontSize: "0.9rem",
                  fontWeight: 800,
                  fontFamily: "monospace",
                  color: style.text,
                }}>
                  {s.score >= 0 ? "+" : ""}{s.score.toFixed(0)}
                </span>
                <span style={{
                  fontSize: "0.6rem",
                  color: "var(--text-tertiary)",
                }}>
                  {DIR_LABELS[s.direction]}
                </span>
              </div>

              {/* Hover tooltip */}
              {isHovered && (
                <div style={{
                  position: "absolute",
                  bottom: "calc(100% + 6px)",
                  left: "50%",
                  transform: "translateX(-50%)",
                  background: "rgba(15, 23, 42, 0.95)",
                  border: `1px solid ${style.border}`,
                  borderRadius: 8,
                  padding: "8px 12px",
                  fontSize: "0.72rem",
                  whiteSpace: "nowrap",
                  zIndex: 10,
                  boxShadow: `0 4px 16px ${style.border}33`,
                  pointerEvents: "none",
                }}>
                  <div style={{ fontWeight: 700, marginBottom: 3 }}>
                    {s.name} <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>{s.symbol}</span>
                  </div>
                  <div style={{ display: "flex", gap: 12 }}>
                    <span>分数 <strong style={{ color: style.text }}>{s.score >= 0 ? "+" : ""}{s.score.toFixed(1)}</strong></span>
                    <span>现价 <strong>¥{s.current_price.toFixed(3)}</strong></span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div style={{
        display: "flex",
        gap: "1rem",
        justifyContent: "center",
        marginTop: 8,
        fontSize: "0.6rem",
        color: "var(--text-tertiary)",
      }}>
        {[
          { label: "强买/买入", color: "#22c55e" },
          { label: "观望", color: "#64748b" },
          { label: "卖出/强卖", color: "#ef4444" },
        ].map((l) => (
          <span key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{
              width: 8, height: 8, borderRadius: 2,
              background: l.color, opacity: 0.6,
            }} />
            {l.label}
          </span>
        ))}
        <span>色深 = 信号强度</span>
      </div>
    </div>
  );
}
