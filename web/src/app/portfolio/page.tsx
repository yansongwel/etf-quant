"use client";

import { useEffect, useState, useCallback } from "react";
import { pnl as fmtPnl, pnlPct as fmtPnlPct } from "@/lib/format";
import ErrorBanner from "@/components/ErrorBanner";
import EquityChart from "@/components/EquityChart";

const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

interface HoldingInput {
  symbol: string;
  buy_price: string;
  shares: string;
  note: string;
}

interface PositionAdvice {
  symbol: string;
  name: string;
  buy_price: number;
  shares: number;
  cost: number;
  current_price: number;
  market_value: number;
  pnl: number;
  pnl_pct: number;
  action: string;
  action_color: string;
  urgency: number;
  reasons: string[];
  rsi_14: number;
  momentum_20d: number;
  flow_type: string;
  signal_direction: string;
  target_price: number;
  stop_loss: number;
  suggested_action: string;
}

interface PortfolioAnalysis {
  total_positions: number;
  total_cost: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  health_score: number;
  winners: number;
  losers: number;
  urgent_count: number;
  action_summary: Record<string, number>;
  overall_strategy: string;
  positions: PositionAdvice[];
  disclaimer: string;
}

interface SavedHolding {
  symbol: string;
  buy_price: number;
  shares: number;
  cost: number;
  buy_date: string;
  note: string;
}

const ACTION_COLORS: Record<string, string> = {
  red: "#ef4444",
  orange: "#f97316",
  yellow: "#eab308",
  green: "#22c55e",
};

const FLOW_LABELS: Record<string, string> = {
  accumulation: "吸筹",
  distribution: "出货",
  breakout_buy: "突破",
  panic_sell: "恐慌",
  normal: "-",
};

const EMPTY_INPUT: HoldingInput = { symbol: "", buy_price: "", shares: "", note: "" };

export default function PortfolioPage() {
  const [analysis, setAnalysis] = useState<PortfolioAnalysis | null>(null);
  const [holdings, setHoldings] = useState<SavedHolding[]>([]);
  const [loading, setLoading] = useState(false);
  const [newHolding, setNewHolding] = useState<HoldingInput>({ ...EMPTY_INPUT });
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [selectedPos, setSelectedPos] = useState<string | null>(null);
  const [equityCurve, setEquityCurve] = useState<{ date: string; value: number }[]>([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [listRes, analysisRes, curveRes] = await Promise.allSettled([
        fetch("/api/portfolio/list").then((r) => r.json()),
        fetch("/api/portfolio/analyze").then((r) => {
          if (!r.ok) return null;
          return r.json();
        }),
        fetch("/api/portfolio/equity-curve?days=60").then((r) => {
          if (!r.ok) return null;
          return r.json();
        }),
      ]);
      if (listRes.status === "fulfilled") setHoldings(listRes.value.holdings || []);
      if (analysisRes.status === "fulfilled" && analysisRes.value) setAnalysis(analysisRes.value);
      if (curveRes.status === "fulfilled" && curveRes.value?.curve) setEquityCurve(curveRes.value.curve);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载持仓失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addHolding = async () => {
    if (!newHolding.symbol || !newHolding.buy_price || !newHolding.shares) {
      setError("请填写完整：代码、买入价、数量");
      return;
    }
    setAdding(true);
    setError("");
    try {
      const res = await fetch("/api/portfolio/add", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(API_KEY ? { "X-API-Key": API_KEY } : {}) },
        body: JSON.stringify({
          symbol: newHolding.symbol,
          buy_price: parseFloat(newHolding.buy_price),
          shares: parseInt(newHolding.shares),
          note: newHolding.note,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "添加失败");
      }
      setNewHolding({ ...EMPTY_INPUT });
      setShowForm(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "添加失败");
    } finally {
      setAdding(false);
    }
  };

  const removeHolding = async (symbol: string) => {
    try {
      await fetch("/api/portfolio/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(API_KEY ? { "X-API-Key": API_KEY } : {}) },
        body: JSON.stringify({ symbol }),
      });
      await refresh();
    } catch {
      /* ignore */
    }
  };

  const positions = analysis?.positions ?? [];

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800 }}>我的持仓</h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 2 }}>
            录入持仓后自动监控：到达目标价/止损价时提醒卖出 | {holdings.length} 个持仓
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {showForm ? "取消" : "+ 添加持仓"}
          </button>
          <button className="btn btn-secondary" onClick={refresh} disabled={loading}>
            {loading ? "分析中..." : "刷新分析"}
          </button>
        </div>
      </div>

      {/* Add holding form */}
      {showForm && (
        <div className="card" style={{ marginBottom: "1.5rem", borderColor: "var(--accent)", borderWidth: 2 }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.75rem" }}>添加持仓</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1.5fr auto", gap: "0.75rem", alignItems: "end" }}>
            <div>
              <label className="metric-label" style={{ display: "block", marginBottom: 4 }}>ETF代码</label>
              <input
                className="input"
                placeholder="如 510300"
                value={newHolding.symbol}
                onChange={(e) => setNewHolding({ ...newHolding, symbol: e.target.value })}
                maxLength={6}
              />
            </div>
            <div>
              <label className="metric-label" style={{ display: "block", marginBottom: 4 }}>买入价格</label>
              <input
                className="input"
                type="number"
                placeholder="4.500"
                step="0.001"
                value={newHolding.buy_price}
                onChange={(e) => setNewHolding({ ...newHolding, buy_price: e.target.value })}
              />
            </div>
            <div>
              <label className="metric-label" style={{ display: "block", marginBottom: 4 }}>买入数量</label>
              <input
                className="input"
                type="number"
                placeholder="10000"
                step="100"
                value={newHolding.shares}
                onChange={(e) => setNewHolding({ ...newHolding, shares: e.target.value })}
              />
            </div>
            <div>
              <label className="metric-label" style={{ display: "block", marginBottom: 4 }}>备注</label>
              <input
                className="input"
                placeholder="可选备注"
                value={newHolding.note}
                onChange={(e) => setNewHolding({ ...newHolding, note: e.target.value })}
              />
            </div>
            <button className="btn btn-primary" onClick={addHolding} disabled={adding} style={{ padding: "0.6rem 1.5rem" }}>
              {adding ? "添加中..." : "确认添加"}
            </button>
          </div>
          {error && <div style={{ color: "var(--red)", fontSize: "0.85rem", marginTop: 8 }}>{error}</div>}
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 8 }}>
            数量必须是100的整数倍（ETF最小交易单位）| 同一ETF再次添加会自动合并计算均价
          </div>
        </div>
      )}

      {/* ─── Equity Curve ─── */}
      {equityCurve.length > 2 && (
        <div style={{ marginBottom: "1.25rem" }}>
          <EquityChart data={equityCurve} height={220} />
        </div>
      )}

      {/* Portfolio summary */}
      {analysis && (
        <>
          {/* Health + P&L bar */}
          <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem" }}>
            <div className="card" style={{ flex: 2, borderColor: analysis.health_score > 60 ? "var(--green)" : analysis.health_score > 30 ? "var(--yellow)" : "var(--red)", borderWidth: 2 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <div>
                  <div style={{ fontSize: "2.5rem", fontWeight: 800, color: analysis.health_score > 60 ? "var(--green)" : analysis.health_score > 30 ? "var(--yellow)" : "var(--red)" }}>
                    {analysis.health_score}
                  </div>
                  <div className="metric-label">健康分</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: 4 }}>{analysis.overall_strategy}</div>
                  <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                    {analysis.winners} 盈 / {analysis.losers} 亏 | 紧急处理: {analysis.urgent_count}
                  </div>
                </div>
              </div>
            </div>
            <div className="card" style={{ flex: 1, textAlign: "center" }}>
              <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>总成本</div>
              <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>¥{analysis.total_cost.toLocaleString()}</div>
            </div>
            <div className="card" style={{ flex: 1, textAlign: "center" }}>
              <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>总市值</div>
              <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>¥{analysis.total_value.toLocaleString()}</div>
            </div>
            <div className="card" style={{ flex: 1, textAlign: "center" }}>
              <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>总盈亏</div>
              <div style={{ fontSize: "1.3rem", fontWeight: 800, color: analysis.total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                {fmtPnl(analysis.total_pnl)}
              </div>
              <div style={{ fontSize: "0.85rem", color: analysis.total_pnl_pct >= 0 ? "var(--green)" : "var(--red)" }}>
                {fmtPnlPct(analysis.total_pnl_pct)}
              </div>
            </div>
          </div>

          {/* ─── Sell Timing Monitor ─── */}
          {positions.length > 0 && (
            <div className="card" style={{ marginBottom: "1rem", padding: "0.85rem 1rem" }}>
              <h3 style={{ fontSize: "0.9rem", fontWeight: 700, marginBottom: 8, color: "var(--text-primary)" }}>
                卖出时机监控
              </h3>
              <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginBottom: 8 }}>
                当现价触及目标价或止损价时，系统会在"告警"中提醒你操作
              </div>
              <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", fontSize: "0.7rem", color: "var(--text-secondary)" }}>
                    <th style={{ textAlign: "left", padding: "4px 0" }}>持仓</th>
                    <th style={{ textAlign: "right", padding: "4px 0" }}>现价</th>
                    <th style={{ textAlign: "right", padding: "4px 0" }}>目标价(止盈)</th>
                    <th style={{ textAlign: "right", padding: "4px 0" }}>止损价</th>
                    <th style={{ textAlign: "right", padding: "4px 0" }}>距止盈</th>
                    <th style={{ textAlign: "right", padding: "4px 0" }}>距止损</th>
                    <th style={{ textAlign: "center", padding: "4px 0" }}>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => {
                    const toTarget = p.target_price > 0 ? ((p.target_price - p.current_price) / p.current_price * 100) : 0;
                    const toStop = p.stop_loss > 0 ? ((p.current_price - p.stop_loss) / p.current_price * 100) : 0;
                    const nearTarget = toTarget > 0 && toTarget < 2;
                    const nearStop = toStop > 0 && toStop < 2;
                    return (
                      <tr key={p.symbol} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "6px 0", fontWeight: 600 }}>
                          <span className="mono">{p.symbol}</span>
                          <span style={{ marginLeft: 6, color: "var(--text-secondary)", fontWeight: 400 }}>{p.name}</span>
                        </td>
                        <td className="mono" style={{ textAlign: "right", fontWeight: 600 }}>¥{p.current_price.toFixed(3)}</td>
                        <td className="mono" style={{ textAlign: "right", color: "var(--green)", fontWeight: 600 }}>
                          {p.target_price > 0 ? `¥${p.target_price.toFixed(3)}` : "—"}
                        </td>
                        <td className="mono" style={{ textAlign: "right", color: "var(--red)", fontWeight: 600 }}>
                          {p.stop_loss > 0 ? `¥${p.stop_loss.toFixed(3)}` : "—"}
                        </td>
                        <td className="mono" style={{ textAlign: "right", color: "var(--green)" }}>
                          {toTarget > 0 ? `+${toTarget.toFixed(1)}%` : "—"}
                        </td>
                        <td className="mono" style={{ textAlign: "right", color: "var(--red)" }}>
                          {toStop > 0 ? `-${toStop.toFixed(1)}%` : "—"}
                        </td>
                        <td style={{ textAlign: "center" }}>
                          {nearTarget && <span style={{ padding: "2px 6px", borderRadius: 4, background: "rgba(34,197,94,0.12)", color: "var(--green)", fontSize: "0.7rem", fontWeight: 600 }}>接近止盈</span>}
                          {nearStop && <span style={{ padding: "2px 6px", borderRadius: 4, background: "rgba(239,68,68,0.12)", color: "var(--red)", fontSize: "0.7rem", fontWeight: 600 }}>接近止损</span>}
                          {!nearTarget && !nearStop && <span style={{ color: "var(--text-tertiary)", fontSize: "0.7rem" }}>正常</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Urgent alerts */}
          {positions.filter(p => p.urgency >= 4).length > 0 && (
            <div className="card" style={{ marginBottom: "1rem", borderColor: "var(--red)", borderWidth: 2, background: "rgba(239,68,68,0.04)" }}>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--red)", marginBottom: 8 }}>
                需要紧急处理 ({positions.filter(p => p.urgency >= 4).length})
              </h3>
              {positions.filter(p => p.urgency >= 4).map(p => (
                <div key={p.symbol} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <div>
                    <span style={{ fontFamily: "monospace", fontWeight: 700 }}>{p.symbol}</span>
                    <span style={{ marginLeft: 6, color: "var(--text-secondary)" }}>{p.name}</span>
                    <span style={{ marginLeft: 8, color: ACTION_COLORS[p.action_color], fontWeight: 700 }}>{p.action}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span style={{ color: p.pnl >= 0 ? "var(--green)" : "var(--red)", fontWeight: 700 }}>
                      {fmtPnlPct(p.pnl_pct)}
                    </span>
                    <span style={{ marginLeft: 8, fontSize: "0.8rem", color: "var(--text-secondary)" }}>{p.suggested_action}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Position cards */}
      {positions.length > 0 && (
        <div style={{ display: "grid", gap: "0.75rem" }}>
          {positions.map((p) => (
            <div
              key={p.symbol}
              className="card"
              onClick={() => setSelectedPos(selectedPos === p.symbol ? null : p.symbol)}
              style={{
                cursor: "pointer",
                borderLeft: `4px solid ${ACTION_COLORS[p.action_color]}`,
                background: p.urgency >= 4 ? `${ACTION_COLORS[p.action_color]}08` : undefined,
              }}
            >
              {/* Row 1: Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontFamily: "monospace", fontWeight: 800, fontSize: "1.1rem" }}>{p.symbol}</span>
                  <span style={{ color: "var(--text-secondary)" }}>{p.name}</span>
                  <span style={{
                    padding: "3px 10px", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700,
                    color: "white", background: ACTION_COLORS[p.action_color],
                  }}>
                    {p.action}
                  </span>
                  {p.urgency >= 4 && (
                    <span style={{ fontSize: "0.7rem", padding: "2px 6px", borderRadius: 4, background: "rgba(239,68,68,0.1)", color: "var(--red)", fontWeight: 600 }}>
                      紧急
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "1.3rem", fontWeight: 800, color: p.pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                      {fmtPnl(p.pnl)}
                    </div>
                    <div style={{ fontSize: "0.8rem", color: p.pnl_pct >= 0 ? "var(--green)" : "var(--red)" }}>
                      {fmtPnlPct(p.pnl_pct)}
                    </div>
                  </div>
                  <button
                    className="btn btn-secondary"
                    onClick={(e) => { e.stopPropagation(); removeHolding(p.symbol); }}
                    style={{ padding: "2px 8px", fontSize: "0.7rem" }}
                    title="删除此持仓"
                  >
                    删除
                  </button>
                </div>
              </div>

              {/* Row 2: Metrics */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8, marginBottom: 8 }}>
                {[
                  { label: "买入价", value: `¥${p.buy_price.toFixed(3)}` },
                  { label: "现价", value: `¥${p.current_price.toFixed(3)}` },
                  { label: "持仓量", value: `${p.shares.toLocaleString()}股` },
                  { label: "成本", value: `¥${p.cost.toLocaleString()}` },
                  { label: "市值", value: `¥${p.market_value.toLocaleString()}` },
                  { label: "RSI", value: `${p.rsi_14}`, color: p.rsi_14 > 70 ? "var(--red)" : p.rsi_14 < 30 ? "var(--green)" : undefined },
                ].map((m, i) => (
                  <div key={i} style={{ background: "var(--bg-primary)", borderRadius: 6, padding: "6px 8px", textAlign: "center" }}>
                    <div style={{ fontSize: "0.65rem", color: "var(--text-secondary)" }}>{m.label}</div>
                    <div style={{ fontWeight: 600, fontSize: "0.85rem", color: m.color }}>{m.value}</div>
                  </div>
                ))}
              </div>

              {/* Row 3: Action suggestion */}
              <div style={{ padding: "8px 10px", borderRadius: 6, background: `${ACTION_COLORS[p.action_color]}10`, border: `1px solid ${ACTION_COLORS[p.action_color]}30` }}>
                <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>操作建议: </span>
                <span style={{ fontSize: "0.85rem" }}>{p.suggested_action}</span>
              </div>

              {/* Expanded detail */}
              {selectedPos === p.symbol && (
                <div style={{ marginTop: 10, padding: "10px", background: "var(--bg-primary)", borderRadius: 8 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>动量20日</div>
                      <div style={{ fontWeight: 700, color: p.momentum_20d > 0 ? "var(--green)" : "var(--red)" }}>
                        {p.momentum_20d > 0 ? "+" : ""}{p.momentum_20d}%
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>资金流</div>
                      <div style={{ fontWeight: 700 }}>{FLOW_LABELS[p.flow_type] || p.flow_type}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--green)" }}>目标价</div>
                      <div style={{ fontWeight: 700, color: "var(--green)" }}>¥{p.target_price.toFixed(3)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--red)" }}>止损价</div>
                      <div style={{ fontWeight: 700, color: "var(--red)" }}>¥{p.stop_loss.toFixed(3)}</div>
                    </div>
                  </div>
                  <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                    <span style={{ fontWeight: 600 }}>分析: </span>
                    {p.reasons.join(" | ")}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 4 }}>
                    量化信号: {p.signal_direction}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {holdings.length === 0 && !loading && (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <div style={{ fontSize: "2rem", marginBottom: 8 }}>📋</div>
          <h3 style={{ fontWeight: 700, marginBottom: 8 }}>还没有持仓数据</h3>
          <p style={{ color: "var(--text-secondary)", marginBottom: 16 }}>
            点击"添加持仓"输入你的ETF持仓信息，系统将实时分析每个持仓并给出操作建议
          </p>
          <button className="btn btn-primary" onClick={() => setShowForm(true)}>
            + 添加第一个持仓
          </button>
        </div>
      )}

      {analysis && (
        <div style={{ marginTop: "1rem", fontSize: "0.75rem", color: "var(--text-secondary)", textAlign: "center" }}>
          {analysis.disclaimer}
        </div>
      )}
    </div>
  );
}
