"use client";

import { useState, useCallback, useEffect } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import CapitalInput from "@/components/CapitalInput";
import RiskGauge from "@/components/RiskGauge";

interface ETFRiskProfile {
  symbol: string;
  name: string;
  risk_level: string;
  risk_label: string;
  risk_score: number;
  volatility_20d: number;
  max_drawdown_60d: number;
  rsi_14: number;
  momentum_20d: number;
  volume_ratio: number;
  flow_type: string;
  warnings: string[];
  suggestions: string[];
}

interface LayoutSuggestion {
  symbol: string;
  name: string;
  action: string;
  reason: string;
  entry_strategy: string;
  position_pct: number;
  stop_loss_pct: number;
  risk_level: string;
  risk_label: string;
  confidence: number;
  timeframe: string;
}

interface RiskRule {
  rule: string;
  value: string;
  priority: string;
}

interface RiskReport {
  capital: number;
  portfolio_risk: string;
  portfolio_risk_label: string;
  avg_risk_score: number;
  high_risk_count: number;
  total_etfs: number;
  risk_profiles: ETFRiskProfile[];
  layout_suggestions: LayoutSuggestion[];
  risk_rules: RiskRule[];
  disclaimer: string;
}

const RISK_COLORS: Record<string, string> = {
  low: "#22c55e",
  medium: "#eab308",
  high: "#ef4444",
  extreme: "#9333ea",
};

export default function RiskPage() {
  const [capital, setCapital] = useState(500000);
  const [report, setReport] = useState<RiskReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"layout" | "risk" | "rules">("layout");

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/risk/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ capital }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setReport(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setLoading(false);
    }
  }, [capital]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const profiles = report?.risk_profiles ?? [];
  const layouts = report?.layout_suggestions ?? [];
  const rules = report?.risk_rules ?? [];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>风险控制 & 布局建议</h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 4 }}>
            多维风险评估 + 提前布局策略 + 止损规则
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <CapitalInput value={capital} onChange={setCapital} compact />
          <button className="btn btn-primary" onClick={loadReport} disabled={loading}>
            {loading ? "分析中..." : "生成报告"}
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={`风控报告加载失败: ${error}`} onRetry={loadReport} />}

      {/* Portfolio risk summary */}
      {report && (
        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
          {/* Risk Gauge */}
          <div className="card" style={{ borderColor: RISK_COLORS[report.portfolio_risk], borderWidth: 2, display: "flex", alignItems: "center", justifyContent: "center", padding: "0.5rem 1.5rem" }}>
            <RiskGauge score={report.avg_risk_score} label="组合风险分" size={170} />
          </div>

          {/* KPI cards */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
            <div className="card" style={{ textAlign: "center", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ fontSize: "2rem", fontWeight: 800 }}>{layouts.filter(l => l.position_pct > 0).length}</div>
              <div className="metric-label">布局机会</div>
            </div>
            <div className="card" style={{ textAlign: "center", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ fontSize: "2rem", fontWeight: 800, color: "var(--red)" }}>
                {layouts.filter(l => l.action.includes("减仓")).length}
              </div>
              <div className="metric-label">需减仓</div>
            </div>
            <div className="card" style={{ textAlign: "center", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ fontSize: "2rem", fontWeight: 800 }}>{report.total_etfs}</div>
              <div className="metric-label">ETF总数</div>
            </div>
            <div className="card" style={{ textAlign: "center", gridColumn: "span 3", padding: "0.5rem" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                <span style={{ color: RISK_COLORS[report.portfolio_risk], fontWeight: 700 }}>{report.portfolio_risk_label}</span>
                <span style={{ margin: "0 6px" }}>·</span>
                高风险 {report.high_risk_count}/{report.total_etfs} 只
                <span style={{ margin: "0 6px" }}>·</span>
                平均风险分 {report.avg_risk_score.toFixed(1)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab navigation */}
      {report && (
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          {[
            { id: "layout" as const, label: `布局建议 (${layouts.length})` },
            { id: "risk" as const, label: `风险概览 (${profiles.length})` },
            { id: "rules" as const, label: `风控规则 (${rules.length})` },
          ].map((t) => (
            <button
              key={t.id}
              className={`btn ${tab === t.id ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* Layout suggestions tab */}
      {report && tab === "layout" && (
        <div>
          {layouts.map((s, i) => (
            <div
              key={i}
              className="card"
              style={{
                marginBottom: "0.75rem",
                borderLeft: `4px solid ${RISK_COLORS[s.risk_level]}`,
                background: s.action.includes("提前布局") || s.action.includes("吸筹") ? "rgba(34,197,94,0.04)" : s.action.includes("减仓") ? "rgba(239,68,68,0.04)" : undefined,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 800, fontSize: "1.1rem" }}>{s.action}</span>
                    <span style={{ fontFamily: "monospace", fontWeight: 600 }}>{s.symbol}</span>
                    <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>{s.name}</span>
                  </div>
                  <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: 4 }}>{s.reason}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "1.25rem", fontWeight: 800, color: RISK_COLORS[s.risk_level] }}>
                    {s.confidence}%
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>置信度</div>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem", marginBottom: 8 }}>
                <div style={{ background: "var(--bg-primary)", borderRadius: 6, padding: "8px", textAlign: "center" }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>建议仓位</div>
                  <div style={{ fontWeight: 700, color: s.position_pct > 0 ? "var(--green)" : "var(--text-secondary)" }}>
                    {s.position_pct}%
                  </div>
                </div>
                <div style={{ background: "var(--bg-primary)", borderRadius: 6, padding: "8px", textAlign: "center" }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>止损比例</div>
                  <div style={{ fontWeight: 700, color: "var(--red)" }}>{s.stop_loss_pct}%</div>
                </div>
                <div style={{ background: "var(--bg-primary)", borderRadius: 6, padding: "8px", textAlign: "center" }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>风险等级</div>
                  <div style={{ fontWeight: 700, color: RISK_COLORS[s.risk_level] }}>{s.risk_label}</div>
                </div>
                <div style={{ background: "var(--bg-primary)", borderRadius: 6, padding: "8px", textAlign: "center" }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>持仓周期</div>
                  <div style={{ fontWeight: 700 }}>{s.timeframe}</div>
                </div>
              </div>

              <div style={{ fontSize: "0.85rem", padding: "8px 10px", background: "var(--bg-primary)", borderRadius: 6 }}>
                <span style={{ fontWeight: 600 }}>入场策略: </span>
                <span style={{ color: "var(--text-secondary)" }}>{s.entry_strategy}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Risk profiles tab */}
      {report && tab === "risk" && (
        <div>
          <table className="data-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>风险</th>
                <th>风险分</th>
                <th>波动率</th>
                <th>回撤</th>
                <th>RSI</th>
                <th>动量</th>
                <th>量比</th>
                <th>资金流</th>
                <th>警告</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((p) => (
                <tr key={p.symbol}>
                  <td style={{ fontFamily: "monospace", fontWeight: 600 }}>{p.symbol}</td>
                  <td>{p.name}</td>
                  <td>
                    <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.75rem", fontWeight: 700, color: "white", background: RISK_COLORS[p.risk_level] }}>
                      {p.risk_label}
                    </span>
                  </td>
                  <td style={{ fontWeight: 700, color: RISK_COLORS[p.risk_level] }}>{p.risk_score}</td>
                  <td>{p.volatility_20d}%</td>
                  <td style={{ color: p.max_drawdown_60d > 10 ? "var(--red)" : "inherit" }}>{p.max_drawdown_60d}%</td>
                  <td style={{ color: p.rsi_14 > 70 ? "var(--red)" : p.rsi_14 < 30 ? "var(--green)" : "inherit" }}>{p.rsi_14}</td>
                  <td style={{ color: p.momentum_20d > 0 ? "var(--green)" : "var(--red)" }}>{p.momentum_20d}%</td>
                  <td style={{ color: p.volume_ratio >= 2 ? "var(--red)" : "inherit" }}>{p.volume_ratio}x</td>
                  <td style={{ fontSize: "0.75rem" }}>{p.flow_type}</td>
                  <td style={{ fontSize: "0.75rem", maxWidth: 200 }}>
                    {p.warnings.length > 0 ? (
                      <span style={{ color: "var(--red)" }}>{p.warnings[0]}</span>
                    ) : (
                      <span style={{ color: "var(--green)" }}>-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Risk rules tab */}
      {report && tab === "rules" && (
        <div>
          <div style={{ display: "grid", gap: "0.75rem" }}>
            {rules.map((r, i) => (
              <div key={i} className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: "1rem" }}>{r.rule}</div>
                  <div style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginTop: 4 }}>{r.value}</div>
                </div>
                <span style={{
                  padding: "4px 12px", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700,
                  background: r.priority === "必须执行" ? "rgba(239,68,68,0.1)" : "rgba(234,179,8,0.1)",
                  color: r.priority === "必须执行" ? "var(--red)" : "var(--yellow)",
                  border: `1px solid ${r.priority === "必须执行" ? "rgba(239,68,68,0.3)" : "rgba(234,179,8,0.3)"}`,
                }}>
                  {r.priority}
                </span>
              </div>
            ))}
          </div>

          <div className="card" style={{ marginTop: "1.5rem", background: "rgba(59,130,246,0.05)", borderColor: "var(--accent)" }}>
            <h4 style={{ fontWeight: 700, marginBottom: 8 }}>资金管理公式（¥{(capital / 10000).toFixed(0)}万）</h4>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem", fontSize: "0.9rem" }}>
              <div>
                <div className="metric-label">单笔最大亏损</div>
                <div style={{ fontWeight: 700, fontSize: "1.2rem", color: "var(--red)" }}>
                  ¥{(capital * 0.02).toLocaleString()}
                </div>
              </div>
              <div>
                <div className="metric-label">熔断线(总亏5%)</div>
                <div style={{ fontWeight: 700, fontSize: "1.2rem", color: "var(--red)" }}>
                  ¥{(capital * 0.05).toLocaleString()}
                </div>
              </div>
              <div>
                <div className="metric-label">现金保留</div>
                <div style={{ fontWeight: 700, fontSize: "1.2rem", color: "var(--green)" }}>
                  ¥{(capital * 0.15).toLocaleString()}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {report && (
        <div style={{ marginTop: "1rem", fontSize: "0.75rem", color: "var(--text-secondary)", textAlign: "center" }}>
          {report.disclaimer}
        </div>
      )}
    </div>
  );
}
