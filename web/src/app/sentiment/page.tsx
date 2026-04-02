"use client";

import { useEffect, useState, useCallback } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import RefreshTimer from "@/components/RefreshTimer";

interface NewsItem {
  title: string;
  content: string;
  time: string;
  date: string;
  category: string;
  sectors: string[];
  direction: string;
  importance: string;
}

interface FeedResponse {
  count: number;
  news: NewsItem[];
  summary: {
    bullish: number;
    bearish: number;
    neutral: number;
    high_importance: number;
    mood: string;
  };
  generated_at: string;
}

const CAT_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  global: { label: "全球", icon: "🌍", color: "#3b82f6" },
  china: { label: "中国", icon: "🇨🇳", color: "#ef4444" },
  industry: { label: "行业", icon: "🏭", color: "#f59e0b" },
};

const DIR_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  bullish: { color: "#22c55e", bg: "rgba(34,197,94,0.08)", label: "利多" },
  bearish: { color: "#ef4444", bg: "rgba(239,68,68,0.08)", label: "利空" },
  neutral: { color: "#64748b", bg: "rgba(100,116,139,0.05)", label: "中性" },
};

const IMP_STYLES: Record<string, { color: string; label: string }> = {
  high: { color: "#ef4444", label: "重要" },
  medium: { color: "#f59e0b", label: "关注" },
  low: { color: "#64748b", label: "" },
};

const MOOD_STYLES: Record<string, { color: string; icon: string }> = {
  "偏多": { color: "#22c55e", icon: "📈" },
  "偏空": { color: "#ef4444", icon: "📉" },
  "中性": { color: "#f59e0b", icon: "↔️" },
};

export default function SentimentPage() {
  const [data, setData] = useState<FeedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [catFilter, setCatFilter] = useState("");
  const [impFilter, setImpFilter] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (catFilter) params.set("category", catFilter);
      if (impFilter) params.set("importance", impFilter);
      const res = await fetch(`/api/sentiment/feed?${params}`);
      if (!res.ok) throw new Error("加载失败");
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [catFilter, impFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const summary = data?.summary;
  const moodStyle = MOOD_STYLES[summary?.mood || "中性"] || MOOD_STYLES["中性"];

  return (
    <div className="fade-in">
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800 }}>市场舆情</h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 2 }}>
            实时财经新闻 · 自动标注影响板块和方向 · 辅助交易决策
            {data?.generated_at && (
              <span style={{ marginLeft: 8, color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
                {data.generated_at} CST
              </span>
            )}
          </p>
        </div>
        <RefreshTimer intervalSec={300} onRefresh={refresh} loading={loading} />
      </div>

      {error && <ErrorBanner message={error} onRetry={refresh} />}

      {/* Mood + Summary */}
      {summary && (
        <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem" }}>
          <div className="card" style={{ flex: 2, display: "flex", alignItems: "center", gap: 12, borderColor: moodStyle.color, borderWidth: 2 }}>
            <span style={{ fontSize: "2rem" }}>{moodStyle.icon}</span>
            <div>
              <div style={{ fontSize: "1.3rem", fontWeight: 800, color: moodStyle.color }}>
                市场情绪: {summary.mood}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                利多 {summary.bullish} · 利空 {summary.bearish} · 中性 {summary.neutral} · 重要事件 {summary.high_importance}
              </div>
            </div>
          </div>
          <div className="card" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#22c55e" }}>{summary.bullish}</div>
            <div className="metric-label">利多信号</div>
          </div>
          <div className="card" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#ef4444" }}>{summary.bearish}</div>
            <div className="metric-label">利空信号</div>
          </div>
          <div className="card" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "1.8rem", fontWeight: 800 }}>{data?.count || 0}</div>
            <div className="metric-label">总条数</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: "0.3rem" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", marginRight: 4 }}>分类:</span>
          {[
            { key: "", label: "全部" },
            { key: "global", label: "🌍 全球" },
            { key: "china", label: "🇨🇳 中国" },
            { key: "industry", label: "🏭 行业" },
          ].map((f) => (
            <button key={f.key} onClick={() => setCatFilter(f.key)}
              style={{
                padding: "4px 10px", borderRadius: 6, fontSize: "0.75rem",
                border: `1.5px solid ${catFilter === f.key ? "var(--accent)" : "var(--border)"}`,
                background: catFilter === f.key ? "var(--accent-glow)" : "transparent",
                color: catFilter === f.key ? "var(--accent)" : "var(--text-secondary)",
                fontWeight: catFilter === f.key ? 700 : 500, cursor: "pointer",
              }}
            >{f.label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: "0.3rem" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", marginRight: 4 }}>重要性:</span>
          {[
            { key: "", label: "全部" },
            { key: "high", label: "重要" },
            { key: "medium", label: "关注" },
          ].map((f) => (
            <button key={f.key} onClick={() => setImpFilter(f.key)}
              style={{
                padding: "4px 10px", borderRadius: 6, fontSize: "0.75rem",
                border: `1.5px solid ${impFilter === f.key ? "var(--accent)" : "var(--border)"}`,
                background: impFilter === f.key ? "var(--accent-glow)" : "transparent",
                color: impFilter === f.key ? "var(--accent)" : "var(--text-secondary)",
                fontWeight: impFilter === f.key ? 700 : 500, cursor: "pointer",
              }}
            >{f.label}</button>
          ))}
        </div>
      </div>

      {loading && !data && <LoadingSkeleton rows={6} height={60} />}

      {/* News Feed */}
      {data && data.news.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {data.news.map((item, i) => {
            const cat = CAT_LABELS[item.category] || CAT_LABELS.china;
            const dir = DIR_STYLES[item.direction] || DIR_STYLES.neutral;
            const imp = IMP_STYLES[item.importance] || IMP_STYLES.low;

            return (
              <div key={i} className="card" style={{
                padding: "0.65rem 0.85rem",
                borderLeft: `3px solid ${dir.color}`,
                background: dir.bg,
              }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                  {/* Time + category */}
                  <div style={{ flexShrink: 0, minWidth: 56, textAlign: "right" }}>
                    <div style={{ fontSize: "0.72rem", fontFamily: "monospace", color: "var(--text-tertiary)" }}>
                      {item.time ? item.time.slice(0, 5) : ""}
                    </div>
                    <div style={{ fontSize: "0.6rem", color: cat.color, fontWeight: 600, marginTop: 1 }}>
                      {cat.icon} {cat.label}
                    </div>
                  </div>

                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.82rem", fontWeight: 600, lineHeight: 1.4 }}>
                      {imp.label && (
                        <span style={{
                          display: "inline-block", padding: "1px 6px", borderRadius: 3,
                          fontSize: "0.6rem", fontWeight: 700, color: "#fff",
                          background: imp.color, marginRight: 6, verticalAlign: "middle",
                        }}>{imp.label}</span>
                      )}
                      {item.title}
                    </div>
                    {item.content && (
                      <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: 3, lineHeight: 1.4 }}>
                        {item.content}
                      </div>
                    )}

                    {/* Tags */}
                    <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap", alignItems: "center" }}>
                      <span style={{
                        padding: "1px 6px", borderRadius: 3, fontSize: "0.6rem",
                        fontWeight: 700, color: dir.color,
                        background: `${dir.color}15`, border: `1px solid ${dir.color}30`,
                      }}>{dir.label}</span>
                      {item.sectors.map((s) => (
                        <span key={s} style={{
                          padding: "1px 6px", borderRadius: 3, fontSize: "0.6rem",
                          color: "var(--text-secondary)",
                          background: "var(--bg-primary)", border: "1px solid var(--border)",
                        }}>{s}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {data && data.news.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: "2rem", color: "var(--text-tertiary)" }}>
          当前筛选条件下没有新闻
        </div>
      )}

      <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", textAlign: "center", padding: "1rem 0" }}>
        数据来源: 财联社全球快讯 · 百度财经日历 · 5 分钟自动刷新 · 舆情仅供参考，不构成投资建议
      </div>
    </div>
  );
}
