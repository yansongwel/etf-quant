"use client";

/**
 * Semi-circular risk gauge — SVG-based, zero dependencies.
 * 0-100 scale: 0-30 green (low), 30-60 yellow (medium), 60-100 red (high).
 */

interface RiskGaugeProps {
  score: number;       // 0-100
  label?: string;      // e.g., "组合风险分"
  size?: number;       // diameter in px
}

export default function RiskGauge({ score, label = "风险分", size = 160 }: RiskGaugeProps) {
  const clampedScore = Math.max(0, Math.min(100, score));

  // Arc geometry
  const cx = size / 2;
  const cy = size * 0.6;
  const r = size * 0.4;
  const startAngle = Math.PI;      // 180deg (left)
  const endAngle = 0;               // 0deg (right)
  const sweepAngle = startAngle - endAngle;
  const scoreAngle = startAngle - (clampedScore / 100) * sweepAngle;

  // Color based on score
  const color =
    clampedScore >= 60 ? "#ef4444" :
    clampedScore >= 30 ? "#f59e0b" : "#22c55e";

  const riskLabel =
    clampedScore >= 60 ? "高风险" :
    clampedScore >= 30 ? "中风险" : "低风险";

  // Arc path helper
  const arc = (startA: number, endA: number, radius: number) => {
    const x1 = cx + radius * Math.cos(startA);
    const y1 = cy - radius * Math.sin(startA);
    const x2 = cx + radius * Math.cos(endA);
    const y2 = cy - radius * Math.sin(endA);
    const largeArc = startA - endA > Math.PI ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 0 ${x2} ${y2}`;
  };

  // Tick marks at 0, 30, 60, 100
  const ticks = [0, 30, 60, 100].map((v) => {
    const a = startAngle - (v / 100) * sweepAngle;
    const x1 = cx + (r + 4) * Math.cos(a);
    const y1 = cy - (r + 4) * Math.sin(a);
    const x2 = cx + (r + 10) * Math.cos(a);
    const y2 = cy - (r + 10) * Math.sin(a);
    const tx = cx + (r + 18) * Math.cos(a);
    const ty = cy - (r + 18) * Math.sin(a);
    return { x1, y1, x2, y2, tx, ty, v };
  });

  // Needle endpoint
  const nx = cx + (r - 8) * Math.cos(scoreAngle);
  const ny = cy - (r - 8) * Math.sin(scoreAngle);

  return (
    <div style={{ textAlign: "center" }}>
      <svg width={size} height={size * 0.7} viewBox={`0 0 ${size} ${size * 0.7}`}>
        {/* Background arc segments: green → yellow → red */}
        <path d={arc(startAngle, startAngle - 0.3 * sweepAngle, r)} fill="none" stroke="#22c55e" strokeWidth={8} strokeLinecap="round" opacity={0.2} />
        <path d={arc(startAngle - 0.3 * sweepAngle, startAngle - 0.6 * sweepAngle, r)} fill="none" stroke="#f59e0b" strokeWidth={8} strokeLinecap="round" opacity={0.2} />
        <path d={arc(startAngle - 0.6 * sweepAngle, endAngle, r)} fill="none" stroke="#ef4444" strokeWidth={8} strokeLinecap="round" opacity={0.2} />

        {/* Active arc */}
        <path d={arc(startAngle, scoreAngle, r)} fill="none" stroke={color} strokeWidth={8} strokeLinecap="round" />

        {/* Tick marks */}
        {ticks.map((t) => (
          <g key={t.v}>
            <line x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} stroke="#475569" strokeWidth={1} />
            <text x={t.tx} y={t.ty} textAnchor="middle" dominantBaseline="middle" fontSize={9} fill="#64748b">{t.v}</text>
          </g>
        ))}

        {/* Needle */}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={color} strokeWidth={2.5} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={4} fill={color} />
        <circle cx={cx} cy={cy} r={2} fill="#0f172a" />

        {/* Score text */}
        <text x={cx} y={cy - 16} textAnchor="middle" fontSize={22} fontWeight={800} fill={color} fontFamily="monospace">
          {clampedScore.toFixed(1)}
        </text>
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize={9} fill="#64748b">
          {label}
        </text>
      </svg>

      {/* Risk label badge */}
      <div style={{
        display: "inline-block",
        padding: "3px 12px",
        borderRadius: 6,
        background: `${color}15`,
        color,
        fontWeight: 700,
        fontSize: "0.8rem",
        marginTop: -4,
      }}>
        {riskLabel}
      </div>
    </div>
  );
}
