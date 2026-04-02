"use client";

import type { TradeRecord } from "@/lib/api";
import { num } from "@/lib/format";

interface TradesTableProps {
  trades: TradeRecord[];
  maxRows?: number;
}

export default function TradesTable({ trades, maxRows = 20 }: TradesTableProps) {
  const display = trades.slice(-maxRows).reverse();

  if (display.length === 0) {
    return (
      <div className="card">
        <h3 style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>交易记录</h3>
        <p style={{ color: "var(--text-secondary)", marginTop: 12, fontSize: "0.85rem" }}>
          暂无交易记录
        </p>
      </div>
    );
  }

  return (
    <div className="card" style={{ overflow: "auto" }}>
      <h3 style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
        最近交易 ({trades.length} 笔)
      </h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>执行日期</th>
            <th>信号日期</th>
            <th>代码</th>
            <th>方向</th>
            <th>价格</th>
            <th>数量</th>
            <th>佣金</th>
          </tr>
        </thead>
        <tbody>
          {display.map((t, i) => (
            <tr key={i}>
              <td>{t.date}</td>
              <td style={{ color: "var(--text-secondary)" }}>{t.signal_date}</td>
              <td style={{ fontWeight: 600 }}>{t.symbol}</td>
              <td>
                <span
                  style={{
                    color: t.side === "buy" ? "var(--red)" : "var(--green)",
                    fontWeight: 600,
                  }}
                >
                  {t.side === "buy" ? "买入" : "卖出"}
                </span>
              </td>
              <td>{num(t.price)}</td>
              <td>{t.shares.toLocaleString()}</td>
              <td style={{ color: "var(--text-secondary)" }}>¥{t.commission.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
