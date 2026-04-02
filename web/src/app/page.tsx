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
  tier: "action" | "watch" | "reference" | "noise";
}

interface SignalSummary {
  count: number;
  signals: Signal[];
  summary: Record<string, number>;
  tiers?: Record<string, number>;
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

const TIER_ICON: Record<string, string> = { action: "🔴", watch: "🟡", reference: "⚪" };
const TIER_LABEL: Record<string, string> = { action: "立即行动", watch: "关注观察", reference: "仅供参考" };
const TIER_ACC: Record<string, string> = { action: "≈80%", watch: "≈58%", reference: "≈57%" };

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

  // Load sparkline trends for action+watch signals
  useEffect(() => {
    if (!signals?.signals) return;
    const actionable = signals.signals.filter(s => s.tier === "action" || s.tier === "watch").slice(0, 10);
    for (const s of actionable) {
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

  const tiers = signals?.tiers;
  const actionCount = tiers?.action || 0;
  const watchCount = tiers?.watch || 0;

  // Actionable signals: action + watch, sorted by abs(score)
  const actionableSignals = (signals?.signals || [])
    .filter(s => s.tier === "action" || s.tier === "watch")
    .sort((a, b) => Math.abs(b.score) - Math.abs(a.score));

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
          scrollbarWidth: "none",
        }}>
          {realtimeQuotes.map((q) => (
            <div key={q.symbol} style={{
              flex: "0 0 auto", padding: "4px 10px", borderRadius: 6,
              background: q.change_pct > 0 ? "rgba(34,197,94,0.1)" : q.change_pct < 0 ? "rgba(239,68,68,0.1)" : "var(--bg-secondary)",
              fontSize: "0.75rem", whiteSpace: "nowrap",
            }}>
              <span style={{ fontWeight: 600 }}>{q.name}</span>
              <span className="mono" style={{
                marginLeft: 6, fontWeight: 700,
                color: q.change_pct > 0 ? "var(--green)" : q.change_pct < 0 ? "var(--red)" : "inherit",
              }}>
                {q.change_pct > 0 ? "+" : ""}{q.change_pct.toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={refresh} />}
      {loading && !signals && <LoadingSkeleton rows={5} height={60} />}

      {/* ─── Verdict Banner ─── */}
      {verdict && (
        <Link href="/signals" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card" style={{
            marginBottom: "1rem", borderLeft: `4px solid ${verdict.color || "#60a5fa"}`,
            cursor: "pointer", transition: "all 0.15s",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <div style={{ fontSize: "1.5rem", fontWeight: 800, color: verdict.color }}>{verdict.verdict}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.9rem", fontWeight: 600 }}>{verdict.action}</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{verdict.signal_summary}</div>
              </div>
              <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "var(--accent)" }}>查看详情 →</span>
            </div>
          </div>
        </Link>
      )}

      {/* ─── Alerts ─── */}
      {alerts.length > 0 && (
        <div className="card" style={{
          marginBottom: "1rem", borderColor: "var(--red)", borderWidth: 2,
          background: "rgba(239,68,68,0.06)",
        }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--red)", marginBottom: 4 }}>
            止盈止损告警 ({alerts.length})
          </div>
          {alerts.map((a, i) => (
            <div key={i} style={{ fontSize: "0.8rem", padding: "2px 0" }}>
              <span className="mono" style={{ fontWeight: 700, marginRight: 6 }}>{a.symbol}</span>
              <span style={{ color: a.alert_type === "stop_loss" ? "var(--red)" : "var(--green)" }}>
                {a.message}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ─── Tier Quick Cards ─── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: "0.75rem", marginBottom: "1.25rem" }}>
        <Link href="/signals" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card" style={{ textAlign: "center", cursor: "pointer", transition: "all 0.15s", borderColor: actionCount > 0 ? "#ef4444" : "var(--border)", borderWidth: actionCount > 0 ? 2 : 1 }}>
            <div style={{ fontSize: "0.85rem", marginBottom: 2 }}>🔴</div>
            <div style={{ fontSize: "2rem", fontWeight: 800, color: actionCount > 0 ? "#ef4444" : "var(--text-tertiary)" }}>{actionCount}</div>
            <div style={{ fontSize: "0.8rem", fontWeight: 600 }}>立即行动</div>
            <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)" }}>准确率≈80%</div>
          </div>
        </Link>
        <Link href="/signals" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card" style={{ textAlign: "center", cursor: "pointer", transition: "all 0.15s", borderColor: watchCount > 0 ? "#eab308" : "var(--border)", borderWidth: watchCount > 0 ? 2 : 1 }}>
            <div style={{ fontSize: "0.85rem", marginBottom: 2 }}>🟡</div>
            <div style={{ fontSize: "2rem", fontWeight: 800, color: watchCount > 0 ? "#eab308" : "var(--text-tertiary)" }}>{watchCount}</div>
            <div style={{ fontSize: "0.8rem", fontWeight: 600 }}>关注观察</div>
            <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)" }}>准确率≈58%</div>
          </div>
        </Link>
        <Link href="/portfolio" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card" style={{ textAlign: "center", cursor: "pointer", transition: "all 0.15s" }}>
            <div style={{ fontSize: "2rem", fontWeight: 800 }}>{portfolio?.total_positions || 0}</div>
            <div style={{ fontSize: "0.8rem", fontWeight: 600 }}>我的持仓</div>
            <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)" }}>
              {portfolio ? `${portfolio.total_pnl >= 0 ? "+" : ""}${portfolio.total_pnl_pct.toFixed(1)}%` : "管理持仓 →"}
            </div>
          </div>
        </Link>
        <Link href="/sector" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card" style={{ textAlign: "center", cursor: "pointer", transition: "all 0.15s" }}>
            <div style={{ fontSize: "2rem", fontWeight: 800 }}>{sectorData.length}</div>
            <div style={{ fontSize: "0.8rem", fontWeight: 600 }}>板块轮动</div>
            <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)" }}>
              {sectorData.filter(s => s.phase === "recovery").length} 个复苏期
            </div>
          </div>
        </Link>
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

      {/* ─── Actionable Signal Table ─── */}
      {actionableSignals.length > 0 && (
        <div className="card" style={{ padding: "1rem", marginBottom: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div className="section-title">值得关注的信号</div>
            <Link href="/signals" style={{ fontSize: "0.8rem", color: "var(--accent)", textDecoration: "none" }}>
              查看全部 →
            </Link>
          </div>
          <table className="data-table" style={{ fontSize: "0.8rem" }}>
            <thead>
              <tr>
                <th>名称</th>
                <th>级别</th>
                <th>信号</th>
                <th style={{ textAlign: "right" }}>评分</th>
                <th style={{ textAlign: "center" }}>30日趋势</th>
                <th style={{ textAlign: "right" }}>现价</th>
                <th style={{ textAlign: "right" }}>目标/止损</th>
              </tr>
            </thead>
            <tbody>
              {actionableSignals.slice(0, 10).map((s) => (
                <tr key={s.symbol}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{s.name || s.symbol}</div>
                    <div className="mono" style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>{s.symbol}</div>
                  </td>
                  <td>
                    <span style={{ fontSize: "0.75rem" }}>{TIER_ICON[s.tier] || ""}</span>
                    <span style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", marginLeft: 4 }}>
                      {TIER_ACC[s.tier] || ""}
                    </span>
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
                  <td className="tabular" style={{ textAlign: "right" }}>
                    <span style={{ color: "var(--green)" }}>{num(s.target_price, 3)}</span>
                    <span style={{ color: "var(--text-tertiary)", margin: "0 2px" }}>/</span>
                    <span style={{ color: "var(--red)" }}>{num(s.stop_loss, 3)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {actionableSignals.length === 0 && (
            <div style={{ textAlign: "center", padding: "1rem", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
              当前没有高置信信号 — 平均每12天出现1个action级信号
            </div>
          )}
        </div>
      )}

      {/* ─── Footer ─── */}
      <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", textAlign: "center", padding: "0.5rem 0" }}>
        仅供研究参考，不构成投资建议。Score≥50 信号 T+5 准确率≈80%。
      </div>
    </div>
  );
}
