"use client";

import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { HistDataPoint } from "@/lib/api";
import { shortDate, num } from "@/lib/format";

interface PriceChartProps {
  data: HistDataPoint[];
  height?: number;
}

export default function PriceChart({ data, height = 400 }: PriceChartProps) {
  if (data.length === 0) {
    return (
      <div className="card" style={{ height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "var(--text-secondary)" }}>选择 ETF 查看行情</span>
      </div>
    );
  }

  // Add color info for volume bars
  const chartData = data.map((d, i) => ({
    ...d,
    volumeColor: d.close >= d.open ? "rgba(34, 197, 94, 0.4)" : "rgba(239, 68, 68, 0.4)",
    priceChange: i > 0 ? d.close - data[i - 1].close : 0,
  }));

  return (
    <div className="card">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="date" tickFormatter={shortDate} stroke="#64748b" fontSize={11} tickLine={false} />
          <YAxis
            yAxisId="price"
            domain={["auto", "auto"]}
            stroke="#64748b"
            fontSize={11}
            tickLine={false}
            tickFormatter={(v: number) => num(v, 2)}
            width={55}
          />
          <YAxis yAxisId="volume" orientation="right" stroke="#64748b" fontSize={10} tickLine={false} hide />
          <Tooltip
            contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
            formatter={(value, name) => {
              const v = Number(value);
              if (name === "volume") return [v.toLocaleString(), "成交量"];
              return [num(v), name === "close" ? "收盘" : name === "high" ? "最高" : name === "low" ? "最低" : "开盘"];
            }}
          />
          <Bar yAxisId="volume" dataKey="volume" fill="rgba(100, 116, 139, 0.2)" />
          <Line yAxisId="price" type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={1.5} dot={false} />
          <Line yAxisId="price" type="monotone" dataKey="high" stroke="rgba(34, 197, 94, 0.3)" strokeWidth={0.5} dot={false} />
          <Line yAxisId="price" type="monotone" dataKey="low" stroke="rgba(239, 68, 68, 0.3)" strokeWidth={0.5} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
