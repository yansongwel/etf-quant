"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { SignalData, SignalsResponse, PositionsResponse, SignalDetail, SignalTrendPoint } from "@/lib/api";
import { num, nowCST } from "@/lib/format";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import SignalTrendChart from "@/components/SignalTrendChart";
import RefreshTimer from "@/components/RefreshTimer";
import CapitalInput from "@/components/CapitalInput";
import ExportButton from "@/components/ExportButton";

/* ─── Constants ─── */

const DIR_LABELS: Record<string, string> = {
  strong_buy: "强烈买入",
  buy: "买入",
  hold: "持有观望",
  sell: "卖出",
  strong_sell: "强烈卖出",
};

const DIR_COLORS: Record<string, string> = {
  strong_buy: "#22c55e",
  buy: "#4ade80",
  hold: "#94a3b8",
  sell: "#f87171",
  strong_sell: "#ef4444",
};

const TIER_CONFIG: Record<string, { label: string; icon: string; color: string; bg: string; desc: string }> = {
  action: {
    label: "立即行动",
    icon: "🔴",
    color: "#ef4444",
    bg: "rgba(239,68,68,0.08)",
    desc: "高置信信号 · 买入持有3-5天(T+5≈68%) · 卖出10天内减仓(T+10≈76%)",
  },
  watch: {
    label: "关注观察",
    icon: "🟡",
    color: "#eab308",
    bg: "rgba(234,179,8,0.08)",
    desc: "中等置信 · 准确率≈58% · 纳入观察列表等待升级",
  },
  reference: {
    label: "仅供参考",
    icon: "⚪",
    color: "#94a3b8",
    bg: "rgba(148,163,184,0.06)",
    desc: "边际信号 · 准确率≈57% · 不建议单独操作",
  },
};

type TierKey = "action" | "watch" | "reference";

/* ─── Page ─── */

export default function SignalsPage() {
  const [signalData, setSignalData] = useState<SignalsResponse | null>(null);
  const [positions, setPositions] = useState<PositionsResponse | null>(null);
  const [capital, setCapital] = useState(500000);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");
  const [alerts, setAlerts] = useState<Array<{ symbol: string; alert_type: string; message: string }>>([]);
  const [selectedDetail, setSelectedDetail] = useState<SignalDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTier, setActiveTier] = useState<TierKey>("action");
  const [trendCache, setTrendCache] = useState<Record<string, SignalTrendPoint[]>>({});
  const [trendLoading, setTrendLoading] = useState<Set<string>>(new Set());
  const [showHold, setShowHold] = useState(false);

  const loadTrend = useCallback(async (symbol: string) => {
    if (trendCache[symbol] || trendLoading.has(symbol)) return;
    setTrendLoading((prev) => new Set(prev).add(symbol));
    try {
      const res = await api.signalTrend(symbol, 60);
      setTrendCache((prev) => ({ ...prev, [symbol]: res.trend }));
    } catch {
      /* trend is optional */
    } finally {
      setTrendLoading((prev) => {
        const next = new Set(prev);
        next.delete(symbol);
        return next;
      });
    }
  }, [trendCache, trendLoading]);

  const loadDetail = async (symbol: string) => {
    if (selectedDetail?.symbol === symbol) {
      setSelectedDetail(null);
      return;
    }
    setDetailLoading(true);
    try {
      const detail = await api.signalDetail(symbol);
      setSelectedDetail(detail);
    } catch {
      setSelectedDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sigs, pos, alertRes] = await Promise.all([
        api.signals(),
        api.positions(capital),
        api.signalAlerts().catch(() => ({ alerts: [] })),
      ]);
      setSignalData(sigs);
      setPositions(pos);
      setAlerts(alertRes?.alerts || []);
      setLastUpdate(sigs?.generated_at || nowCST());
    } catch (e) {
      setError(e instanceof Error ? e.message : "信号数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [capital]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const sigs = signalData?.signals ?? [];
  const tiers = signalData?.tiers;

  // Load trends for action/watch signals
  useEffect(() => {
    const actionSignals = sigs.filter((s) => s.tier === "action" || s.tier === "watch");
    for (const s of actionSignals.slice(0, 15)) {
      loadTrend(s.symbol);
    }
  }, [sigs, loadTrend]);

  // Group signals by tier
  const actionSignals = sigs.filter((s) => s.tier === "action").sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  const watchSignals = sigs.filter((s) => s.tier === "watch").sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  const referenceSignals = sigs.filter((s) => s.tier === "reference").sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  const holdSignals = sigs.filter((s) => s.tier === "noise");

  const activeSignals = activeTier === "action" ? actionSignals : activeTier === "watch" ? watchSignals : referenceSignals;

  // Match position data to buy signals
  const posMap = new Map((positions?.positions ?? []).map((p) => [p.symbol, p]));

  return (
    <div className="fade-in">
      {/* ─── Header ─── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800 }}>交易信号 V5.0</h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 2 }}>
            非对称信号引擎 · 按置信度分级 · {lastUpdate ? `${lastUpdate} CST` : "加载中..."}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <CapitalInput value={capital} onChange={setCapital} compact />
          <RefreshTimer intervalSec={60} onRefresh={refresh} loading={loading} />
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={refresh} />}
      {loading && !signalData && <LoadingSkeleton rows={4} height={70} />}

      {/* ─── Tier Summary ─── */}
      {tiers && (
        <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.25rem" }}>
          {(["action", "watch", "reference"] as TierKey[]).map((t) => {
            const cfg = TIER_CONFIG[t];
            const count = tiers[t] || 0;
            const isActive = activeTier === t;
            return (
              <button
                key={t}
                onClick={() => setActiveTier(t)}
                style={{
                  flex: 1,
                  padding: "0.85rem",
                  borderRadius: 10,
                  border: `2px solid ${isActive ? cfg.color : "var(--border)"}`,
                  background: isActive ? cfg.bg : "var(--bg-primary)",
                  cursor: "pointer",
                  transition: "all 0.15s",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: "0.85rem", marginBottom: 4 }}>{cfg.icon}</div>
                <div style={{ fontSize: "1.8rem", fontWeight: 800, color: cfg.color }}>{count}</div>
                <div style={{ fontSize: "0.75rem", fontWeight: isActive ? 700 : 500, color: isActive ? "var(--text-primary)" : "var(--text-secondary)" }}>
                  {cfg.label}
                </div>
              </button>
            );
          })}
          <div
            className="card"
            style={{
              flex: 1,
              textAlign: "center",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
            }}
          >
            <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#94a3b8" }}>{holdSignals.length}</div>
            <div className="metric-label">观望</div>
          </div>
        </div>
      )}

      {/* ─── Alerts Banner ─── */}
      {alerts.length > 0 && (
        <div className="card" style={{ borderColor: "var(--red)", borderWidth: 2, marginBottom: "1rem", background: "rgba(239,68,68,0.06)" }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--red)", marginBottom: 6 }}>
            止盈止损告警 ({alerts.length})
          </div>
          {alerts.map((a, i) => (
            <div key={i} style={{ fontSize: "0.85rem", padding: "3px 0" }}>
              <span style={{ fontFamily: "monospace", fontWeight: 700, marginRight: 8 }}>{a.symbol}</span>
              <span style={{ color: a.alert_type === "stop_loss" ? "var(--red)" : "var(--green)" }}>
                {a.message}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ─── Buy Plan (for action tier) ─── */}
      {activeTier === "action" && positions && positions.positions.length > 0 && (
        <div id="buy-plan-export" className="card" style={{ marginBottom: "1.25rem", borderColor: "#22c55e", borderWidth: 2, background: "rgba(34,197,94,0.04)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div>
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--green)" }}>
                买入方案 — ¥{(capital / 10000).toFixed(0)}万资金
              </h3>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 2 }}>
                已分配 ¥{positions.invested.toLocaleString()} · 剩余 ¥{positions.remaining.toLocaleString()}
              </p>
            </div>
            <ExportButton targetId="buy-plan-export" filename="买入方案" />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "0.6rem" }}>
            {positions.positions.map((p) => (
              <div
                key={p.symbol}
                style={{
                  background: "var(--bg-primary)",
                  borderRadius: 8,
                  padding: "0.85rem",
                  border: "1px solid rgba(34,197,94,0.2)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: "1rem" }}>{p.name || p.symbol}</span>
                    <span className="mono" style={{ marginLeft: 6, fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{p.symbol}</span>
                  </div>
                  <span style={{ fontWeight: 800, fontSize: "1.1rem", color: "var(--green)" }}>
                    ¥{p.buy_amount.toLocaleString()}
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px", fontSize: "0.8rem" }}>
                  <div>买入价 <strong>{num(p.entry_price, 3)}</strong></div>
                  <div>数量 <strong>{p.shares.toLocaleString()}股</strong></div>
                  <div>目标价 <strong style={{ color: "var(--green)" }}>{num(p.target_price, 3)}</strong></div>
                  <div>止损价 <strong style={{ color: "var(--red)" }}>{num(p.stop_loss, 3)}</strong></div>
                  <div>预期盈利 <strong style={{ color: "var(--green)" }}>¥{p.expected_gain.toFixed(0)}</strong></div>
                  <div>盈亏比 <strong>{p.risk_reward}</strong></div>
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 6 }}>{p.reason}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginTop: 8 }}>{positions.disclaimer}</div>
        </div>
      )}

      {/* ─── Tier Description ─── */}
      <div style={{
        padding: "0.5rem 0.75rem",
        marginBottom: "0.75rem",
        borderRadius: 6,
        background: TIER_CONFIG[activeTier].bg,
        fontSize: "0.8rem",
        color: TIER_CONFIG[activeTier].color,
        fontWeight: 600,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}>
        <span>{TIER_CONFIG[activeTier].icon}</span>
        <span>{TIER_CONFIG[activeTier].desc}</span>
        <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 400 }}>
          {activeSignals.length} 个信号
        </span>
      </div>

      {/* ─── Signal Detail Panel ─── */}
      {selectedDetail && (
        <div className="card" style={{ marginBottom: "1rem", borderColor: DIR_COLORS[selectedDetail.direction], borderWidth: 2 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div>
              <span style={{ fontWeight: 800, fontSize: "1.2rem", fontFamily: "monospace" }}>{selectedDetail.symbol}</span>
              <span style={{ marginLeft: 10, padding: "3px 8px", borderRadius: 5, fontSize: "0.75rem", fontWeight: 700, color: "white", background: DIR_COLORS[selectedDetail.direction] }}>
                {DIR_LABELS[selectedDetail.direction]}
              </span>
            </div>
            <button className="btn btn-secondary" onClick={() => setSelectedDetail(null)} style={{ padding: "3px 10px", fontSize: "0.8rem" }}>
              关闭
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem", marginBottom: "0.75rem" }}>
            {[
              { label: "当前价", value: num(selectedDetail.current_price, 3), color: "inherit" },
              { label: "目标价", value: num(selectedDetail.target_price, 3), color: "var(--green)" },
              { label: "止损价", value: num(selectedDetail.stop_loss, 3), color: "var(--red)" },
              { label: "仓位建议", value: `${(selectedDetail.position_pct * 100).toFixed(1)}%`, color: "inherit" },
            ].map((m) => (
              <div key={m.label} style={{ background: "var(--bg-primary)", borderRadius: 6, padding: "8px", textAlign: "center" }}>
                <div style={{ fontSize: "0.65rem", color: "var(--text-secondary)" }}>{m.label}</div>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: m.color }}>{m.value}</div>
              </div>
            ))}
          </div>

          <h4 style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: "0.4rem" }}>因子详情</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: 4 }}>
            {Object.entries(selectedDetail.factors).map(([key, val]) => {
              const FACTOR_CN: Record<string, string> = {
                momentum_20d: "20日动量", momentum_5d: "5日动量", rsi_14: "RSI(14)",
                ma_ratio_5_20: "MA5/MA20", ma_dev_20d: "MA20偏离", ma_dev_60d: "MA60偏离",
                hvol_20d: "20日波动率", atr_14: "ATR(14)", mdd_60d: "60日回撤",
                price_pctile_120d: "120日分位", volume_ratio: "量比", momentum_accel: "动量加速",
                mfi_14: "资金流指数", obv_trend_20d: "OBV趋势", vol_price_div_10d: "量价背离",
              };
              return (
                <div key={key} style={{ display: "flex", justifyContent: "space-between", padding: "3px 6px", background: "var(--bg-primary)", borderRadius: 4, fontSize: "0.75rem" }}>
                  <span style={{ color: "var(--text-secondary)" }}>{FACTOR_CN[key] || key}</span>
                  <span style={{ fontWeight: 600, fontFamily: "monospace", color: typeof val === "number" && val > 0 ? "var(--green)" : typeof val === "number" && val < 0 ? "var(--red)" : "inherit" }}>
                    {typeof val === "number" ? val.toFixed(4) : val}
                  </span>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 6, fontSize: "0.75rem", color: "var(--text-secondary)" }}>{selectedDetail.reason}</div>
        </div>
      )}
      {detailLoading && (
        <div className="card" style={{ marginBottom: "1rem", textAlign: "center", padding: "0.75rem" }}>加载详情...</div>
      )}

      {/* ─── Signal Cards ─── */}
      {activeSignals.length === 0 && !loading && (
        <div className="card" style={{ textAlign: "center", padding: "2rem", color: "var(--text-secondary)" }}>
          {activeTier === "action"
            ? "当前没有高置信信号 — 这是正常的，平均每12天出现1个"
            : `当前没有${TIER_CONFIG[activeTier].label}信号`}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "0.75rem" }}>
        {activeSignals.map((s) => {
          const pos = posMap.get(s.symbol);
          const isBuy = ["strong_buy", "buy"].includes(s.direction);
          const isSell = ["sell", "strong_sell"].includes(s.direction);
          return (
            <div
              key={s.symbol}
              className="card"
              onClick={() => loadDetail(s.symbol)}
              style={{
                cursor: "pointer",
                borderLeft: `4px solid ${DIR_COLORS[s.direction]}`,
                transition: "all 0.15s",
              }}
            >
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <div>
                  <span style={{ fontWeight: 700, fontSize: "1rem" }}>{s.name || s.symbol}</span>
                  <span className="mono" style={{ marginLeft: 6, fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{s.symbol}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontWeight: 800, fontSize: "1.1rem", color: DIR_COLORS[s.direction] }}>
                    {s.score >= 0 ? "+" : ""}{s.score.toFixed(0)}
                  </span>
                  <span
                    style={{
                      padding: "2px 8px",
                      borderRadius: 5,
                      fontSize: "0.7rem",
                      fontWeight: 700,
                      color: "white",
                      background: DIR_COLORS[s.direction],
                    }}
                  >
                    {DIR_LABELS[s.direction]}
                  </span>
                </div>
              </div>

              {/* Price row */}
              <div style={{ display: "flex", gap: "0.75rem", alignItems: "baseline", marginBottom: 6 }}>
                <div>
                  <span style={{ fontSize: "1.3rem", fontWeight: 700 }}>{num(s.current_price, 3)}</span>
                  <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginLeft: 4 }}>现价</span>
                </div>
                <div style={{ fontSize: "0.8rem" }}>
                  <span style={{ color: "var(--green)" }}>{num(s.target_price, 3)}</span>
                  <span style={{ color: "var(--text-tertiary)", margin: "0 4px" }}>/</span>
                  <span style={{ color: "var(--red)" }}>{num(s.stop_loss, 3)}</span>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", marginLeft: 4 }}>目标/止损</span>
                </div>
              </div>

              {/* Tier badge + accuracy hint */}
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 6,
                padding: "3px 8px",
                borderRadius: 4,
                background: TIER_CONFIG[s.tier]?.bg || "transparent",
                fontSize: "0.7rem",
              }}>
                <span>{TIER_CONFIG[s.tier]?.icon}</span>
                <span style={{ color: TIER_CONFIG[s.tier]?.color, fontWeight: 600 }}>{TIER_CONFIG[s.tier]?.label}</span>
                <span style={{ color: "var(--text-tertiary)", marginLeft: "auto" }}>
                  {isBuy ? `建议持有${s.holding_days || 5}天` : isSell ? `建议${s.holding_days || 10}天内减仓` : ""}
                </span>
              </div>

              {/* Buy amount (if in position plan) */}
              {pos && (
                <div style={{
                  background: "rgba(34,197,94,0.08)",
                  borderRadius: 6,
                  padding: "4px 8px",
                  marginBottom: 6,
                  fontSize: "0.8rem",
                  display: "flex",
                  justifyContent: "space-between",
                }}>
                  <span style={{ color: "var(--green)", fontWeight: 600 }}>
                    买入 ¥{pos.buy_amount.toLocaleString()} · {pos.shares}股
                  </span>
                  <span style={{ color: "var(--text-secondary)" }}>
                    预期 +¥{pos.expected_gain.toFixed(0)}
                  </span>
                </div>
              )}

              {/* Signal Trend Chart */}
              {trendCache[s.symbol] && (
                <div style={{
                  margin: "8px -8px 6px",
                  padding: "4px 4px 0",
                  borderRadius: 8,
                  background: "rgba(15, 23, 42, 0.4)",
                }}>
                  <SignalTrendChart data={trendCache[s.symbol]} height={100} />
                </div>
              )}

              {/* Reason */}
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>{s.reason}</div>

              {/* Strength bar */}
              <div style={{ marginTop: 6 }}>
                <div style={{ height: 3, background: "var(--bg-primary)", borderRadius: 2 }}>
                  <div style={{
                    height: "100%",
                    width: `${Math.min(s.strength, 100)}%`,
                    background: DIR_COLORS[s.direction],
                    borderRadius: 2,
                  }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ─── Hold signals (collapsed) ─── */}
      {holdSignals.length > 0 && (
        <div style={{ marginTop: "1.25rem" }}>
          <button
            onClick={() => setShowHold(!showHold)}
            style={{
              width: "100%",
              padding: "0.6rem",
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--bg-primary)",
              cursor: "pointer",
              fontSize: "0.8rem",
              color: "var(--text-secondary)",
              display: "flex",
              justifyContent: "center",
              gap: 8,
            }}
          >
            <span>{showHold ? "▼" : "▶"}</span>
            <span>持有观望 ({holdSignals.length})</span>
          </button>
          {showHold && (
            <div style={{ marginTop: "0.5rem", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "0.4rem" }}>
              {holdSignals.map((s) => (
                <div
                  key={s.symbol}
                  className="card"
                  style={{ padding: "0.5rem 0.75rem", cursor: "pointer", borderLeft: "3px solid #94a3b8" }}
                  onClick={() => loadDetail(s.symbol)}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{s.name || s.symbol}</span>
                    <span className="mono" style={{ fontSize: "0.8rem", color: "#94a3b8" }}>
                      {s.score >= 0 ? "+" : ""}{s.score.toFixed(0)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── Footer ─── */}
      <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", textAlign: "center", padding: "1rem 0 0.5rem" }}>
        仅供研究参考，不构成投资建议。T+1 规则：今日信号明日开盘执行。Score≥50 信号 T+5 准确率≈80%。
      </div>
    </div>
  );
}
