"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { EquityPoint } from "@/lib/api";
import { shortDate, pct } from "@/lib/format";

interface DrawdownChartProps {
  equityData: EquityPoint[];
  height?: number;
}

export default function DrawdownChart({ equityData, height = 200 }: DrawdownChartProps) {
  if (equityData.length < 2) return null;

  // Calculate drawdown from equity curve
  let peak = equityData[0].value;
  const ddData = equityData.map((d) => {
    if (d.value > peak) peak = d.value;
    const dd = (peak - d.value) / peak;
    return { date: d.date, drawdown: -dd };
  });

  return (
    <div className="card">
      <h3 style={{ fontSize: "0.9rem", marginBottom: "0.75rem", color: "var(--text-secondary)" }}>
        回撤曲线
      </h3>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={ddData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="date" tickFormatter={shortDate} stroke="#64748b" fontSize={11} tickLine={false} />
          <YAxis
            tickFormatter={(v: number) => pct(Math.abs(v))}
            stroke="#64748b"
            fontSize={11}
            tickLine={false}
            width={50}
          />
          <Tooltip
            contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
            formatter={(v) => [pct(Math.abs(Number(v))), "回撤"]}
          />
          <Area type="monotone" dataKey="drawdown" stroke="#ef4444" fill="rgba(239, 68, 68, 0.15)" strokeWidth={1} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
