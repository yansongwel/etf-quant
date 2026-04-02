"use client";

import { useEffect, useState, useCallback } from "react";
import { num, nowCST } from "@/lib/format";
import { useMarketWS } from "@/hooks/useMarketWS";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import SignalHeatmap from "@/components/SignalHeatmap";
import Sparkline from "@/components/Sparkline";
import Link from "next/link";

const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

/* ─── Types ─── */

interface Signal {
  symbol: string;
  name?: string;
  direction: string;
  score: number;
  current_price: number;
  target_price: number;
  stop_loss: number;
  reason: string;
}

interface SignalSummary {
  count: number;
  signals: Signal[];
  summary: Record<string, number>;
  generated_at?: string;
}

interface Verdict {
  verdict: string;
  action: string;
  risk_level: string;
  color: string;
  regime: string;
  signal_summary: string;
  top_buy: { symbol: string; name: string; score: number; price: number } | null;
  alert_count: number;
}

interface AlertData {
  symbol: string;
  alert_type: string;
  current_price: number;
  trigger_price: number;
  message: string;
}

interface PortfolioSummary {
  total_cost: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  total_positions: number;
}

const DIR_COLORS: Record<string, string> = {
  strong_buy: "#22c55e",
  buy: "#4ade80",
  hold: "#94a3b8",
  sell: "#f87171",
  strong_sell: "#ef4444",
};

const DIR_CN: Record<string, string> = {
  strong_buy: "强买",
  buy: "买入",
  hold: "观望",
  sell: "卖出",
  strong_sell: "强卖",
};

/* ─── Page ─── */

export default function HomePage() {
  const [signals, setSignals] = useState<SignalSummary | null>(null);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [alerts, setAlerts] = useState<AlertData[]>([]);
  const [trendCache, setTrendCache] = useState<Record<string, number[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [realtimeQuotes, setRealtimeQuotes] = useState<{ symbol: string; name: string; price: number; change_pct: number }[]>([]);
  const [accuracy, setAccuracy] = useState<{ overall_accuracy: number; by_direction: Record<string, { accuracy: number; total: number }> } | null>(null);
  const [sectorData, setSectorData] = useState<Array<{ sector_name: string; phase: string; phase_label: string; momentum_20d: number; best_etf_name: string }>>([]);
  const { data: wsData, connected: wsConnected } = useMarketWS();

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sigRes, verdictRes, alertRes, portfolioRes] = await Promise.all([
        fetch("/api/signals/current").then((r) => {
          if (!r.ok) throw new Error("信号数据加载失败");
          return r.json();
        }),
        fetch("/market/verdict").then((r) => r.json()).catch(() => null),
        fetch("/api/signals/alerts").then((r) => r.json()).catch(() => ({ alerts: [] })),
        fetch("/api/portfolio/analyze").then((r) => r.json()).catch(() => null),
      ]);
      setSignals(sigRes);
      setVerdict(verdictRes);
      setAlerts(alertRes?.alerts || []);
      if (portfolioRes && portfolioRes.total_positions > 0) setPortfolio(portfolioRes);
      setLastUpdate(sigRes?.generated_at || nowCST());
      fetch("/api/signals/accuracy?days=30").then(r => r.json()).then(setAccuracy).catch(() => {});
      fetch("/api/sector/rotation").then(r => r.json()).then(d => {
        if (d?.sectors) setSectorData(d.sectors);
      }).catch(() => {});
      fetch("/market/realtime").then(r => r.json()).then(d => {
        if (d?.quotes) setRealtimeQuotes(d.quotes);
      }).catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "数据加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (wsData?.type === "market_update" && wsData.quotes) {
      setRealtimeQuotes(wsData.quotes);
      if (wsData.timestamp) setLastUpdate(wsData.timestamp);
    }
  }, [wsData]);

  // Load sparkline trends for top 10 signals
  useEffect(() => {
    if (!signals?.signals) return;
    const top10 = signals.signals.slice(0, 10);
    for (const s of top10) {
      if (trendCache[s.symbol]) continue;
      fetch(`/api/signals/trend/${s.symbol}?days=30`)
        .then((r) => r.json())
        .then((d) => {
          if (d?.trend) {
            setTrendCache((prev) => ({
              ...prev,
              [s.symbol]: d.trend.map((t: { score: number }) => t.score),
            }));
          }
        })
        .catch(() => {});
    }
  }, [signals]); // eslint-disable-line react-hooks/exhaustive-deps

  const buyCount = signals?.signals.filter((s) => ["strong_buy", "buy"].includes(s.direction)).length || 0;
  const sellCount = signals?.signals.filter((s) => ["sell", "strong_sell"].includes(s.direction)).length || 0;

  return (
    <div className="fade-in">
      {/* ─── Header ─── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800, letterSpacing: "-0.02em" }}>今日看板</h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 2 }}>
            {lastUpdate ? `${lastUpdate} CST` : "加载中..."} · {signals?.count || 0} 只 ETF
            {wsConnected && <span style={{ marginLeft: 6, color: "var(--green)", fontSize: "0.7rem" }}>● LIVE</span>}
          </p>
        </div>
        <button className="btn btn-primary" onClick={refresh} disabled={loading}>
          {loading ? "刷新中..." : "刷新"}
        </button>
      </div>

      {/* ─── Realtime Ticker ─── */}
      {realtimeQuotes.length > 0 && (
        <div style={{
          display: "flex", gap: "1rem", overflowX: "auto",
          padding: "0.5rem 0", marginBottom: "0.75rem",
          fontSize: "0.75rem", whiteSpace: "nowrap", scrollbarWidth: "none",
        }}>
          {realtimeQuotes.slice(0, 15).map((q) => (
            <span key={q.symbol} style={{ display: "inline-flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
              <span style={{ color: "var(--text-secondary)" }}>{q.name}</span>
              <span className="mono" style={{ fontWeight: 600 }}>¥{q.price.toFixed(3)}</span>
              <span style={{
                fontWeight: 700, fontSize: "0.7rem",
                color: q.change_pct > 0 ? "var(--green)" : q.change_pct < 0 ? "var(--red)" : "var(--text-tertiary)",
              }}>
                {q.change_pct > 0 ? "+" : ""}{q.change_pct.toFixed(2)}%
              </span>
            </span>
          ))}
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={refresh} />}
      {loading && !signals && <LoadingSkeleton rows={3} height={80} />}

      {/* ─── Market Verdict ─── */}
      {verdict && (
        <div
          className="card"
          style={{
            borderLeft: `4px solid ${verdict.color}`,
            marginBottom: "1rem",
            background: `${verdict.color}08`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: 4 }}>
                {verdict.verdict}
              </div>
              <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                <span>操作: <strong style={{ color: verdict.color }}>{verdict.action}</strong></span>
                <span>风险: <strong>{verdict.risk_level}</strong></span>
                <span>{verdict.signal_summary}</span>
              </div>
            </div>
            {verdict.top_buy && (
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>首选买入</div>
                <div style={{ fontWeight: 700, color: "var(--green)" }}>{verdict.top_buy.name}</div>
                <div className="mono" style={{ fontSize: "0.8rem" }}>¥{verdict.top_buy.price}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── Alerts ─── */}
      {alerts.length > 0 && (
        <div className="card" style={{ marginBottom: "1rem", borderColor: "var(--red)", borderWidth: 2, background: "rgba(239,68,68,0.05)" }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--red)", marginBottom: 6 }}>
            止盈止损告警 ({alerts.length})
          </div>
          {alerts.map((a, i) => (
            <div key={i} style={{ fontSize: "0.8rem", padding: "3px 0" }}>
              <span className="mono" style={{ fontWeight: 600, marginRight: 8 }}>{a.symbol}</span>
              <span style={{ color: a.alert_type === "stop_loss" ? "var(--red)" : "var(--green)" }}>
                {a.message}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ─── Portfolio Banner ─── */}
      {portfolio && (
        <Link href="/portfolio" style={{ textDecoration: "none", color: "inherit" }}>
          <div
            className="card"
            style={{
              marginBottom: "1rem",
              padding: "0.75rem 1rem",
              borderLeft: `4px solid ${portfolio.total_pnl >= 0 ? "var(--green)" : "var(--red)"}`,
              background: portfolio.total_pnl >= 0 ? "rgba(34,197,94,0.05)" : "rgba(239,68,68,0.05)",
              cursor: "pointer",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", fontSize: "0.85rem" }}>
              <span style={{ fontWeight: 700 }}>我的持仓</span>
              <span>
                成本 <strong>¥{(portfolio.total_cost / 10000).toFixed(2)}万</strong>
              </span>
              <span>
                市值 <strong>¥{(portfolio.total_value / 10000).toFixed(2)}万</strong>
              </span>
              <span style={{ color: portfolio.total_pnl >= 0 ? "var(--green)" : "var(--red)", fontWeight: 700 }}>
                {portfolio.total_pnl >= 0 ? "+" : ""}¥{portfolio.total_pnl.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}
                ({portfolio.total_pnl_pct >= 0 ? "+" : ""}{portfolio.total_pnl_pct.toFixed(2)}%)
              </span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{portfolio.total_positions} 只</span>
              <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "var(--accent)" }}>查看详情 →</span>
            </div>
          </div>
        </Link>
      )}

      {/* ─── Quick Action Cards ─── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.75rem", marginBottom: "1.25rem" }}>
        <Link href="/signals" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card" style={{ textAlign: "center", cursor: "pointer", transition: "all 0.15s", borderColor: "#22c55e", borderWidth: buyCount > 0 ? 2 : 1 }}>
            <div style={{ fontSize: "2rem", fontWeight: 800, color: "#22c55e" }}>{buyCount}</div>
            <div style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: 2 }}>可买入信号</div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>查看买入方案 →</div>
          </div>
        </Link>
        <Link href="/signals" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card" style={{ textAlign: "center", cursor: "pointer", transition: "all 0.15s", borderColor: "#ef4444", borderWidth: sellCount > 0 ? 2 : 1 }}>
            <div style={{ fontSize: "2rem", fontWeight: 800, color: "#ef4444" }}>{sellCount}</div>
            <div style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: 2 }}>建议卖出</div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>查看详情 →</div>
          </div>
        </Link>
        <Link href="/portfolio" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card" style={{ textAlign: "center", cursor: "pointer", transition: "all 0.15s" }}>
            <div style={{ fontSize: "2rem", fontWeight: 800 }}>{portfolio?.total_positions || 0}</div>
            <div style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: 2 }}>我的持仓</div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>管理持仓 →</div>
          </div>
        </Link>
        {accuracy && (
          <Link href="/signals" style={{ textDecoration: "none", color: "inherit" }}>
            <div className="card" style={{ textAlign: "center", cursor: "pointer", transition: "all 0.15s", borderColor: accuracy.overall_accuracy >= 55 ? "#60a5fa" : "var(--border)" }}>
              <div style={{
                fontSize: "2rem",
                fontWeight: 800,
                color: accuracy.overall_accuracy >= 55 ? "#60a5fa" : accuracy.overall_accuracy >= 45 ? "var(--text-secondary)" : "var(--text-tertiary)",
              }}>
                {accuracy.overall_accuracy.toFixed(0)}%
              </div>
              <div style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: 2 }}>信号准确率</div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>
                卖出 {accuracy.by_direction?.sell?.accuracy?.toFixed(0) || "—"}% · 买入 {accuracy.by_direction?.buy?.accuracy?.toFixed(0) || "—"}%
              </div>
            </div>
          </Link>
        )}
      </div>

      {/* ─── Sector Rotation Mini ─── */}
      {sectorData.length > 0 && (
        <div className="card" style={{ padding: "0.75rem 1rem", marginBottom: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
            <div className="section-title">板块轮动</div>
            <Link href="/sector" style={{ fontSize: "0.75rem", color: "var(--accent)", textDecoration: "none" }}>详情 →</Link>
          </div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {sectorData.sort((a, b) => b.momentum_20d - a.momentum_20d).map((s) => {
              const phaseColor: Record<string, string> = {
                recovering: "#22c55e", leading: "#3b82f6", weakening: "#eab308", lagging: "#64748b",
              };
              const color = phaseColor[s.phase] || "#64748b";
              return (
                <Link key={s.sector_name} href="/sector" style={{ textDecoration: "none" }}>
                  <div style={{
                    padding: "4px 10px", borderRadius: 6, fontSize: "0.7rem",
                    background: `${color}15`, border: `1px solid ${color}30`,
                    color, fontWeight: 600, whiteSpace: "nowrap",
                    display: "flex", alignItems: "center", gap: 4, cursor: "pointer",
                  }}>
                    <span>{s.phase_label.split(" ")[0]}</span>
                    <span style={{ fontWeight: 700 }}>{s.sector_name}</span>
                    <span style={{ fontFamily: "monospace", fontSize: "0.65rem" }}>
                      {s.momentum_20d > 0 ? "+" : ""}{s.momentum_20d.toFixed(1)}%
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* ─── Signal Heatmap ─── */}
      {signals && signals.signals.length > 0 && (
        <div className="card" style={{ padding: "1rem", marginBottom: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div className="section-title">全市场信号热力图</div>
            <Link href="/signals" style={{ fontSize: "0.8rem", color: "var(--accent)", textDecoration: "none" }}>
              查看详情 →
            </Link>
          </div>
          <SignalHeatmap signals={signals.signals} />
        </div>
      )}

      {/* ─── Signal Table (Top 10 only) ─── */}
      {signals && signals.signals.length > 0 && (
        <div className="card" style={{ padding: "1rem", marginBottom: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div className="section-title">信号概览 (Top 10)</div>
            <Link href="/signals" style={{ fontSize: "0.8rem", color: "var(--accent)", textDecoration: "none" }}>
              查看全部 {signals.count} 只 →
            </Link>
          </div>
          <table className="data-table" style={{ fontSize: "0.8rem" }}>
            <thead>
              <tr>
                <th>名称</th>
                <th>信号</th>
                <th style={{ textAlign: "right" }}>评分</th>
                <th style={{ textAlign: "center" }}>30日趋势</th>
                <th style={{ textAlign: "right" }}>现价</th>
                <th style={{ textAlign: "right" }}>目标价</th>
                <th style={{ textAlign: "right" }}>止损价</th>
              </tr>
            </thead>
            <tbody>
              {signals.signals.slice(0, 10).map((s) => (
                <tr key={s.symbol}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{s.name || s.symbol}</div>
                    <div className="mono" style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>{s.symbol}</div>
                  </td>
                  <td>
                    <span className={`badge ${["strong_buy", "buy"].includes(s.direction) ? "badge-buy" : s.direction === "hold" ? "badge-hold" : "badge-sell"}`}>
                      {DIR_CN[s.direction] || s.direction}
                    </span>
                  </td>
                  <td className="tabular" style={{ textAlign: "right", fontWeight: 600, color: s.score > 0 ? "var(--green)" : s.score < 0 ? "var(--red)" : "var(--text-secondary)" }}>
                    {s.score > 0 ? "+" : ""}{s.score.toFixed(0)}
                  </td>
                  <td style={{ textAlign: "center" }}>
                    {trendCache[s.symbol] ? (
                      <Sparkline data={trendCache[s.symbol]} width={80} height={22} />
                    ) : (
                      <span style={{ color: "var(--text-tertiary)", fontSize: "0.65rem" }}>...</span>
                    )}
                  </td>
                  <td className="tabular" style={{ textAlign: "right" }}>{num(s.current_price, 3)}</td>
                  <td className="tabular" style={{ textAlign: "right", color: "var(--green)" }}>{num(s.target_price, 3)}</td>
                  <td className="tabular" style={{ textAlign: "right", color: "var(--red)" }}>{num(s.stop_loss, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ─── Footer ─── */}
      <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", textAlign: "center", padding: "0.5rem 0" }}>
        仅供研究参考，不构成投资建议。
      </div>
    </div>
  );
}
