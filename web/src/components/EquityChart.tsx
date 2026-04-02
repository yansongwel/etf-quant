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
import { money, shortDate } from "@/lib/format";

interface EquityChartProps {
  data: EquityPoint[];
  height?: number;
}

export default function EquityChart({ data, height = 350 }: EquityChartProps) {
  if (data.length === 0) {
    return (
      <div className="card" style={{ height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "var(--text-secondary)" }}>暂无数据 — 请先运行回测</span>
      </div>
    );
  }

  return (
    <div className="card">
      <h3 style={{ fontSize: "0.9rem", marginBottom: "1rem", color: "var(--text-secondary)" }}>
        净值曲线
      </h3>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            stroke="#64748b"
            fontSize={11}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => money(v)}
            stroke="#64748b"
            fontSize={11}
            tickLine={false}
            width={70}
          />
          <Tooltip
            contentStyle={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(v) => [money(Number(v)), "净值"]}
            labelFormatter={(l) => `日期: ${l}`}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="url(#equityGrad)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
