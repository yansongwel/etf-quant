"use client";

import { useState, useEffect, useCallback } from "react";
import { num } from "@/lib/format";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import CapitalInput from "@/components/CapitalInput";
import ExportButton from "@/components/ExportButton";

interface ETFInfo {
  code: string;
  name: string;
  current_price: number;
}

interface Holding {
  etf_code: string;
  etf_name: string;
  shares: number;
  current_value: number;
}

interface BacktestResult {
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  final_value: number;
  total_profit: number;
}

interface StrategyResult {
  rank: number;
  name: string;
  strategy_type: string;
  etf_pool: ETFInfo[];
  backtest_result: BacktestResult;
  current_holding: Holding[];
  rebalance_note: string;
}

interface ProvenResponse {
  capital: number;
  strategies: StrategyResult[];
  disclaimer: string;
  generated_at?: string;
}

/* ─── Helpers ─── */
function fmtMoney(v: number): string {
  if (v >= 10000) return `¥${(v / 10000).toFixed(1)}万`;
  return `¥${v.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

function riskLabel(mdd: number): { text: string; color: string } {
  if (mdd > 30) return { text: "高风险", color: "#ef4444" };
  if (mdd > 20) return { text: "中风险", color: "#f59e0b" };
  return { text: "低风险", color: "#22c55e" };
}

export default function RecommendPage() {
  const [capital, setCapital] = useState(500000);
  const [result, setResult] = useState<ProvenResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedRank, setExpandedRank] = useState<number | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/recommend/proven", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ capital }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Failed");
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [capital]);

  useEffect(() => {
    run();
  }, [run]);

  return (
    <div className="fade-in">
      {/* ─── Header ─── */}
      <div style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ fontSize: "1.5rem", fontWeight: 800 }}>策略推荐</h2>
        <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 2 }}>
          经 5 年历史回测验证的盈利策略 · 输入资金量查看个性化方案
          {result?.generated_at && (
            <span style={{ marginLeft: 8, color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
              {result.generated_at} CST
            </span>
          )}
        </p>
      </div>

      {/* ─── Capital Input ─── */}
      <div className="card" style={{ marginBottom: "1.25rem", padding: "1rem" }}>
        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontWeight: 600, marginBottom: 8 }}>
          投入资金
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          <CapitalInput value={capital} onChange={setCapital} />
          <button className="btn btn-primary" onClick={run} disabled={loading}
            style={{ padding: "0.6rem 1.5rem", marginLeft: "auto" }}>
            {loading ? "计算中..." : "计算方案"}
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={run} />}
      {loading && !result && <LoadingSkeleton rows={3} height={100} />}

      {/* ─── Comparison Table ─── */}
      {result && result.strategies.length > 0 && (
        <div id="strategy-comparison-export" className="card" style={{ marginBottom: "1.25rem", padding: "1rem", overflowX: "auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 700 }}>
              策略对比 — {fmtMoney(capital)} 资金
            </div>
            <ExportButton targetId="strategy-comparison-export" filename="策略对比" />
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <th style={{ textAlign: "left", padding: "8px 6px", color: "var(--text-secondary)", fontWeight: 600 }}>策略</th>
                <th style={{ textAlign: "right", padding: "8px 6px", color: "var(--text-secondary)", fontWeight: 600 }}>年化</th>
                <th style={{ textAlign: "right", padding: "8px 6px", color: "var(--text-secondary)", fontWeight: 600 }}>预期月入</th>
                <th style={{ textAlign: "right", padding: "8px 6px", color: "var(--text-secondary)", fontWeight: 600 }}>预期周入</th>
                <th style={{ textAlign: "right", padding: "8px 6px", color: "var(--text-secondary)", fontWeight: 600 }}>夏普</th>
                <th style={{ textAlign: "right", padding: "8px 6px", color: "var(--text-secondary)", fontWeight: 600 }}>最大回撤</th>
                <th style={{ textAlign: "right", padding: "8px 6px", color: "var(--text-secondary)", fontWeight: 600 }}>风险</th>
              </tr>
            </thead>
            <tbody>
              {result.strategies.map((s) => {
                const b = s.backtest_result;
                const monthlyIncome = (capital * b.annualized_return / 100) / 12;
                const weeklyIncome = monthlyIncome / 4.33;
                const maxLoss = capital * b.max_drawdown / 100;
                const risk = riskLabel(b.max_drawdown);
                return (
                  <tr key={s.rank} style={{
                    borderBottom: "1px solid var(--border)",
                    cursor: "pointer",
                    background: expandedRank === s.rank ? "var(--accent-glow)" : "transparent",
                  }} onClick={() => setExpandedRank(expandedRank === s.rank ? null : s.rank)}>
                    <td style={{ padding: "10px 6px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{
                          fontWeight: 800, fontSize: "0.85rem",
                          color: s.rank === 1 ? "var(--green)" : "var(--text-secondary)",
                        }}>#{s.rank}</span>
                        <span style={{ fontWeight: 600 }}>{s.name}</span>
                      </div>
                    </td>
                    <td style={{ textAlign: "right", padding: "10px 6px", fontWeight: 700, color: "var(--green)", fontFamily: "monospace" }}>
                      +{b.annualized_return.toFixed(1)}%
                    </td>
                    <td style={{ textAlign: "right", padding: "10px 6px", fontWeight: 700, color: "var(--green)", fontFamily: "monospace" }}>
                      {fmtMoney(monthlyIncome)}
                    </td>
                    <td style={{ textAlign: "right", padding: "10px 6px", fontWeight: 600, color: "var(--green)", fontFamily: "monospace" }}>
                      {fmtMoney(weeklyIncome)}
                    </td>
                    <td style={{ textAlign: "right", padding: "10px 6px", fontWeight: 600, fontFamily: "monospace" }}>
                      {b.sharpe_ratio.toFixed(2)}
                    </td>
                    <td style={{ textAlign: "right", padding: "10px 6px", fontFamily: "monospace" }}>
                      <span style={{ color: "var(--red)" }}>{b.max_drawdown.toFixed(1)}%</span>
                      <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginLeft: 4 }}>
                        ({fmtMoney(maxLoss)})
                      </span>
                    </td>
                    <td style={{ textAlign: "right", padding: "10px 6px" }}>
                      <span style={{
                        padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem",
                        fontWeight: 700, color: risk.color,
                        background: `${risk.color}15`,
                      }}>{risk.text}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", marginTop: 8 }}>
            预期收入基于历史年化收益率估算，实际收益受市场波动影响。点击行展开详情。
          </div>
        </div>
      )}

      {/* ─── Strategy Cards ─── */}
      {result && result.strategies.map((s) => {
        const b = s.backtest_result;
        const monthlyIncome = (capital * b.annualized_return / 100) / 12;
        const weeklyIncome = monthlyIncome / 4.33;
        const risk = riskLabel(b.max_drawdown);
        const isExpanded = expandedRank === s.rank || expandedRank === null;

        return (
          <div
            key={s.rank}
            className="card"
            style={{
              marginBottom: "0.75rem",
              borderLeft: `4px solid ${s.rank === 1 ? "var(--green)" : s.rank === 2 ? "#3b82f6" : "var(--border)"}`,
              cursor: "pointer",
            }}
            onClick={() => setExpandedRank(expandedRank === s.rank ? null : s.rank)}
          >
            {/* ── Card Header: name + income highlight ── */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: isExpanded ? "0.75rem" : 0 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    fontSize: "1.3rem", fontWeight: 800,
                    color: s.rank === 1 ? "var(--green)" : "var(--text-secondary)",
                  }}>#{s.rank}</span>
                  <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>{s.name}</h3>
                  {s.rank === 1 && (
                    <span style={{
                      padding: "2px 8px", background: "var(--green)", color: "white",
                      borderRadius: 4, fontSize: "0.7rem", fontWeight: 700,
                    }}>推荐</span>
                  )}
                  <span style={{
                    padding: "2px 8px", borderRadius: 4, fontSize: "0.65rem",
                    fontWeight: 600, color: risk.color, background: `${risk.color}15`,
                  }}>{risk.text}</span>
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 4 }}>
                  {s.strategy_type === "multifactor" ? "多因子打分" : "动量轮动"} · {s.rebalance_note}
                </div>
              </div>

              {/* Income highlight */}
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>预期月收入</div>
                <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--green)", lineHeight: 1.2 }}>
                  {fmtMoney(monthlyIncome)}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                  周 {fmtMoney(weeklyIncome)} · 年化 +{b.annualized_return.toFixed(1)}%
                </div>
              </div>
            </div>

            {/* ── Expanded Content ── */}
            {isExpanded && (
              <>
                {/* Metrics row */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: "0.4rem", marginBottom: "0.75rem" }}>
                  {[
                    { label: "5年总回报", value: `+${b.total_return.toFixed(0)}%`, color: "var(--green)" },
                    { label: "年化收益", value: `+${b.annualized_return.toFixed(1)}%`, color: "var(--green)" },
                    { label: "夏普比率", value: b.sharpe_ratio.toFixed(2), color: b.sharpe_ratio >= 0.8 ? "var(--green)" : "var(--text-primary)" },
                    { label: "最大回撤", value: `${b.max_drawdown.toFixed(1)}%`, color: "var(--red)" },
                    { label: "最大亏损", value: fmtMoney(capital * b.max_drawdown / 100), color: "var(--red)" },
                    { label: "胜率", value: `${b.win_rate.toFixed(0)}%`, color: "var(--text-primary)" },
                  ].map((m, i) => (
                    <div key={i} style={{ background: "var(--bg-primary)", borderRadius: 6, padding: "6px 8px", textAlign: "center" }}>
                      <div style={{ fontSize: "0.65rem", color: "var(--text-secondary)" }}>{m.label}</div>
                      <div style={{ fontSize: "0.95rem", fontWeight: 700, color: m.color, fontFamily: "monospace" }}>{m.value}</div>
                    </div>
                  ))}
                </div>

                {/* ETF Pool */}
                <div style={{ marginBottom: "0.75rem" }}>
                  <div style={{ fontSize: "0.75rem", fontWeight: 600, marginBottom: 4, color: "var(--text-secondary)" }}>ETF 池</div>
                  <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                    {s.etf_pool.map((etf) => (
                      <span key={etf.code} style={{
                        background: "var(--bg-primary)", borderRadius: 5, padding: "3px 8px",
                        fontSize: "0.75rem", display: "inline-flex", gap: 4, alignItems: "center",
                      }}>
                        <span className="mono" style={{ fontWeight: 600 }}>{etf.code}</span>
                        <span style={{ color: "var(--text-tertiary)" }}>{etf.name}</span>
                        <span className="mono" style={{ fontWeight: 600 }}>¥{num(etf.current_price, 3)}</span>
                      </span>
                    ))}
                  </div>
                </div>

                {/* Current buy recommendation */}
                {s.current_holding.length > 0 && (
                  <div style={{
                    background: "rgba(34, 197, 94, 0.06)", borderRadius: 8, padding: "0.6rem 0.75rem",
                    border: "1px solid rgba(34, 197, 94, 0.2)",
                  }}>
                    <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--green)", marginBottom: 4 }}>
                      当前应买入 — 基于 {fmtMoney(capital)} 资金
                    </div>
                    {s.current_holding.map((h) => (
                      <div key={h.etf_code} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "3px 0" }}>
                        <div>
                          <span className="mono" style={{ fontWeight: 700, fontSize: "0.95rem" }}>{h.etf_code}</span>
                          <span style={{ marginLeft: 6, color: "var(--text-secondary)", fontSize: "0.8rem" }}>{h.etf_name}</span>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <span style={{ fontWeight: 700 }}>{h.shares.toLocaleString()}股</span>
                          <span style={{ marginLeft: 6, color: "var(--text-secondary)", fontSize: "0.8rem" }}>
                            约 {fmtMoney(h.current_value)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        );
      })}

      {/* ─── Disclaimer ─── */}
      {result && (
        <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", textAlign: "center", padding: "0.75rem 0" }}>
          {result.disclaimer} · 预期收入基于历史年化收益，不保证未来表现。最大回撤 = 持有期间可能遭受的最大亏损幅度。
        </div>
      )}
    </div>
  );
}
