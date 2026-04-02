"use client";

/**
 * Tiny inline SVG sparkline — no dependencies, ~0.5KB.
 * Shows a score trend as a polyline with optional zero-line.
 */

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}

export default function Sparkline({ data, width = 80, height = 24, color }: SparklineProps) {
  if (data.length < 2) return null;

  const pad = 2;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const max = Math.max(...data.map(Math.abs), 1);
  const mid = height / 2;

  const points = data
    .map((v, i) => {
      const x = pad + (i / (data.length - 1)) * w;
      const y = mid - (v / max) * (h / 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const lastVal = data[data.length - 1];
  const lineColor = color || (lastVal >= 0 ? "#4ade80" : "#f87171");

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ verticalAlign: "middle" }}>
      {/* Zero line */}
      <line x1={pad} y1={mid} x2={width - pad} y2={mid} stroke="#334155" strokeWidth={0.5} strokeDasharray="2 2" />
      {/* Trend line */}
      <polyline
        points={points}
        fill="none"
        stroke={lineColor}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* End dot */}
      <circle
        cx={pad + w}
        cy={mid - (lastVal / max) * (h / 2)}
        r={2}
        fill={lineColor}
      />
    </svg>
  );
}
