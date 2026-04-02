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

type TabKey = "buy" | "sell" | "hold";

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
  const [activeTab, setActiveTab] = useState<TabKey>("buy");
  const [trendCache, setTrendCache] = useState<Record<string, SignalTrendPoint[]>>({});
  const [trendLoading, setTrendLoading] = useState<Set<string>>(new Set());
  const [accuracy, setAccuracy] = useState<{
    overall_accuracy: number;
    by_direction: Record<string, { accuracy: number; total: number; avg_return: number }>;
    records_checked: number;
    total_signals: number;
  } | null>(null);

  const loadTrend = useCallback(async (symbol: string) => {
    if (trendCache[symbol] || trendLoading.has(symbol)) return;
    setTrendLoading((prev) => new Set(prev).add(symbol));
    try {
      const res = await api.signalTrend(symbol, 60);
      setTrendCache((prev) => ({ ...prev, [symbol]: res.trend }));
    } catch {
      /* trend is optional — silent fail */
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
      const [sigs, pos, alertRes, accRes] = await Promise.all([
        api.signals(),
        api.positions(capital),
        api.signalAlerts().catch(() => ({ alerts: [] })),
        api.signalAccuracy(30).catch(() => null),
      ]);
      setSignalData(sigs);
      setPositions(pos);
      if (accRes) setAccuracy(accRes);
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
  const summary = signalData?.summary;

  // Load trends for active signals
  const activeSignalsRef = sigs;
  useEffect(() => {
    for (const s of activeSignalsRef.slice(0, 20)) {
      loadTrend(s.symbol);
    }
  }, [activeSignalsRef, loadTrend]);

  // Split signals into 3 groups
  const buySignals = sigs.filter((s) => ["strong_buy", "buy"].includes(s.direction)).sort((a, b) => b.score - a.score);
  const sellSignals = sigs.filter((s) => ["sell", "strong_sell"].includes(s.direction)).sort((a, b) => a.score - b.score);
  const holdSignals = sigs.filter((s) => s.direction === "hold").sort((a, b) => b.score - a.score);

  // Match position data to buy signals
  const posMap = new Map((positions?.positions ?? []).map((p) => [p.symbol, p]));

  const TABS: { key: TabKey; label: string; count: number; color: string; desc: string }[] = [
    { key: "buy", label: "建议买入", count: buySignals.length, color: "#22c55e", desc: "信号引擎推荐买入的 ETF，附具体金额和价格" },
    { key: "sell", label: "建议卖出", count: sellSignals.length, color: "#ef4444", desc: "建议减仓或清仓的 ETF" },
    { key: "hold", label: "持有观望", count: holdSignals.length, color: "#94a3b8", desc: "暂无明确方向，继续观察" },
  ];

  const activeSignals = activeTab === "buy" ? buySignals : activeTab === "sell" ? sellSignals : holdSignals;

  return (
    <div className="fade-in">
      {/* ─── Header ─── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800 }}>交易信号</h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 2 }}>
            多因子分析 · T+1 信号 · {lastUpdate ? `${lastUpdate} CST` : "加载中..."}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <CapitalInput value={capital} onChange={setCapital} compact />
          <RefreshTimer intervalSec={60} onRefresh={refresh} loading={loading} />
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={refresh} />}
      {loading && !signalData && <LoadingSkeleton rows={4} height={70} />}

      {/* ─── Summary Row ─── */}
      {summary && (
        <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.25rem" }}>
          <div className="card" style={{ flex: 1, textAlign: "center", borderColor: "#22c55e", borderWidth: (summary.strong_buy || 0) + (summary.buy || 0) > 0 ? 2 : 1 }}>
            <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#22c55e" }}>
              {(summary.strong_buy || 0) + (summary.buy || 0)}
            </div>
            <div className="metric-label">可买入</div>
          </div>
          <div className="card" style={{ flex: 1, textAlign: "center", borderColor: "#ef4444", borderWidth: (summary.sell || 0) + (summary.strong_sell || 0) > 0 ? 2 : 1 }}>
            <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#ef4444" }}>
              {(summary.sell || 0) + (summary.strong_sell || 0)}
            </div>
            <div className="metric-label">建议卖出</div>
          </div>
          <div className="card" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#94a3b8" }}>
              {summary.hold || 0}
            </div>
            <div className="metric-label">观望</div>
          </div>
          <div className="card" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "1.8rem", fontWeight: 800 }}>{sigs.length}</div>
            <div className="metric-label">总计</div>
          </div>
        </div>
      )}

      {/* ─── Accuracy Bar ─── */}
      {accuracy && accuracy.records_checked > 0 && (
        <div
          className="card"
          style={{
            marginBottom: "1rem",
            padding: "0.65rem 1rem",
            display: "flex",
            alignItems: "center",
            gap: "1.5rem",
            flexWrap: "wrap",
            borderColor: "var(--border)",
          }}
        >
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontWeight: 600, whiteSpace: "nowrap" }}>
            近30天信号准确率
          </div>
          {[
            { label: "买入", key: "buy", color: "#22c55e" },
            { label: "卖出", key: "sell", color: "#ef4444" },
            { label: "强卖", key: "strong_sell", color: "#dc2626" },
            { label: "综合", key: "_overall", color: "#60a5fa" },
          ].map((item) => {
            const val =
              item.key === "_overall"
                ? accuracy.overall_accuracy
                : accuracy.by_direction[item.key]?.accuracy ?? 0;
            const total =
              item.key === "_overall"
                ? accuracy.total_signals
                : accuracy.by_direction[item.key]?.total ?? 0;
            if (total === 0) return null;
            return (
              <div key={item.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>{item.label}</span>
                <span
                  style={{
                    fontSize: "0.95rem",
                    fontWeight: 800,
                    fontFamily: "monospace",
                    color: val >= 55 ? item.color : val >= 45 ? "var(--text-secondary)" : "var(--text-tertiary)",
                  }}
                >
                  {val.toFixed(1)}%
                </span>
                <span style={{ fontSize: "0.6rem", color: "var(--text-tertiary)" }}>({total})</span>
              </div>
            );
          })}
          <span style={{ fontSize: "0.6rem", color: "var(--text-tertiary)", marginLeft: "auto" }}>
            {accuracy.records_checked}天/{accuracy.total_signals}信号
          </span>
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

      {/* ─── Buy Plan (when buy tab active and positions available) ─── */}
      {activeTab === "buy" && positions && positions.positions.length > 0 && (
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

      {/* ─── Tab Switcher ─── */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        {TABS.map((t) => {
          const active = activeTab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              style={{
                flex: 1,
                padding: "0.65rem 0.75rem",
                borderRadius: 8,
                border: `2px solid ${active ? t.color : "var(--border)"}`,
                background: active ? `${t.color}10` : "var(--bg-primary)",
                cursor: "pointer",
                transition: "all 0.15s",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
              }}
            >
              <span style={{ fontSize: "1.2rem", fontWeight: 800, color: t.color }}>{t.count}</span>
              <span style={{ fontSize: "0.85rem", fontWeight: active ? 700 : 500, color: active ? "var(--text-primary)" : "var(--text-secondary)" }}>
                {t.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Tab description */}
      <p style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginBottom: "0.75rem" }}>
        {TABS.find((t) => t.key === activeTab)?.desc}
      </p>

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
          当前没有{activeTab === "buy" ? "买入" : activeTab === "sell" ? "卖出" : "观望"}信号
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "0.75rem" }}>
        {activeSignals.map((s) => {
          const pos = posMap.get(s.symbol);
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

      {/* ─── Footer ─── */}
      <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", textAlign: "center", padding: "1rem 0 0.5rem" }}>
        仅供研究参考，不构成投资建议。T+1 规则：今日信号明日开盘执行。
      </div>
    </div>
  );
}
