"use client";

import { useState } from "react";

interface CorrelationHeatmapProps {
  factors: string[];
  matrix: number[][];
}

const FACTOR_CN: Record<string, string> = {
  ret_5d: "5日收益", ret_10d: "10日收益", ret_20d: "20日收益", ret_60d: "60日收益",
  momentum_20d: "20日动量", rsi_14: "RSI", roc_10: "ROC(10)", ma_ratio_5_20: "MA5/20",
  ma_dev_20d: "MA20偏离", ma_dev_60d: "MA60偏离", price_pctile_120d: "120日分位",
  vwap_dev_20d: "VWAP偏离",
  hvol_20d: "20日波动", atr_14: "ATR", mdd_60d: "60日回撤",
  skew_20d: "20日偏度", vol_regime: "波动率体制",
};

function colorForCorr(v: number): string {
  if (v >= 0.8) return "rgba(34, 197, 94, 0.8)";
  if (v >= 0.5) return "rgba(34, 197, 94, 0.5)";
  if (v >= 0.2) return "rgba(34, 197, 94, 0.25)";
  if (v > -0.2) return "rgba(100, 116, 139, 0.1)";
  if (v > -0.5) return "rgba(239, 68, 68, 0.25)";
  if (v > -0.8) return "rgba(239, 68, 68, 0.5)";
  return "rgba(239, 68, 68, 0.8)";
}

export default function CorrelationHeatmap({ factors, matrix }: CorrelationHeatmapProps) {
  const [hovered, setHovered] = useState<{ r: number; c: number } | null>(null);
  const n = factors.length;

  if (n < 2) return null;

  const cellSize = Math.max(24, Math.min(36, 600 / n));

  return (
    <div style={{ overflowX: "auto" }}>
      <div style={{ display: "inline-block", minWidth: "fit-content" }}>
        {/* Header row */}
        <div style={{ display: "flex", marginLeft: cellSize * 3.5 }}>
          {factors.map((f, i) => (
            <div key={i} style={{
              width: cellSize, textAlign: "center",
              fontSize: "0.55rem", color: "var(--text-tertiary)",
              transform: "rotate(-45deg)", transformOrigin: "center",
              whiteSpace: "nowrap", height: cellSize * 1.8,
              display: "flex", alignItems: "flex-end", justifyContent: "center",
            }}>
              {FACTOR_CN[f] || f}
            </div>
          ))}
        </div>

        {/* Matrix rows */}
        {factors.map((rowF, r) => (
          <div key={r} style={{ display: "flex", alignItems: "center" }}>
            {/* Row label */}
            <div style={{
              width: cellSize * 3.5, fontSize: "0.6rem", textAlign: "right",
              paddingRight: 6, color: "var(--text-secondary)", whiteSpace: "nowrap",
              overflow: "hidden", textOverflow: "ellipsis",
            }}>
              {FACTOR_CN[rowF] || rowF}
            </div>

            {/* Cells */}
            {matrix[r].map((v, c) => {
              const isHov = hovered?.r === r && hovered?.c === c;
              const isDiag = r === c;
              return (
                <div
                  key={c}
                  onMouseEnter={() => setHovered({ r, c })}
                  onMouseLeave={() => setHovered(null)}
                  style={{
                    width: cellSize, height: cellSize,
                    background: isDiag ? "rgba(100,116,139,0.15)" : colorForCorr(v),
                    border: isHov ? "1.5px solid var(--text-secondary)" : "0.5px solid rgba(51,65,85,0.3)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: cellSize > 28 ? "0.55rem" : "0.45rem",
                    fontWeight: Math.abs(v) > 0.5 ? 700 : 400,
                    color: isDiag ? "var(--text-tertiary)" : Math.abs(v) > 0.3 ? "#fff" : "var(--text-tertiary)",
                    cursor: "default",
                    transition: "all 0.1s",
                    fontFamily: "monospace",
                  }}
                >
                  {isDiag ? "1" : v.toFixed(2)}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Hover info */}
      {hovered && (
        <div style={{
          marginTop: 8, fontSize: "0.72rem", color: "var(--text-secondary)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ fontWeight: 700 }}>
            {FACTOR_CN[factors[hovered.r]] || factors[hovered.r]}
          </span>
          <span>×</span>
          <span style={{ fontWeight: 700 }}>
            {FACTOR_CN[factors[hovered.c]] || factors[hovered.c]}
          </span>
          <span>=</span>
          <span style={{
            fontWeight: 800, fontSize: "1rem", fontFamily: "monospace",
            color: matrix[hovered.r][hovered.c] > 0 ? "#4ade80" : matrix[hovered.r][hovered.c] < 0 ? "#f87171" : "var(--text-secondary)",
          }}>
            {matrix[hovered.r][hovered.c].toFixed(3)}
          </span>
        </div>
      )}

      {/* Legend */}
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 6, fontSize: "0.55rem", color: "var(--text-tertiary)" }}>
        <span>-1.0</span>
        {[-0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8].map((v) => (
          <span key={v} style={{
            width: 16, height: 10, borderRadius: 2,
            background: colorForCorr(v),
          }} />
        ))}
        <span>+1.0</span>
        <span style={{ marginLeft: 8 }}>红=负相关 绿=正相关</span>
      </div>
    </div>
  );
}
