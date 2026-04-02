"use client";

import { useEffect, useState } from "react";
import PriceChart from "@/components/PriceChart";
import Sparkline from "@/components/Sparkline";
import { api } from "@/lib/api";
import type { ETFInfo, HistDataPoint, QualityReport, QualityOverview } from "@/lib/api";
import { num } from "@/lib/format";

export default function DataPage() {
  const [etfList, setEtfList] = useState<ETFInfo[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [histData, setHistData] = useState<HistDataPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [availableSymbols, setAvailableSymbols] = useState<Set<string>>(new Set());
  const [qualityOverview, setQualityOverview] = useState<QualityOverview | null>(null);
  const [symbolQuality, setSymbolQuality] = useState<QualityReport | null>(null);
  const [showQuality, setShowQuality] = useState(false);

  useEffect(() => {
    api.etfList().then(setEtfList).catch(() => {});
    api.symbols().then((r) => setAvailableSymbols(new Set(r.symbols))).catch(() => {});
    api.dataQuality().then(setQualityOverview).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    setSymbolQuality(null);
    Promise.all([
      api.hist(selected, 500).then((r) => setHistData(r.data)).catch(() => setHistData([])),
      api.dataQualitySymbol(selected).then(setSymbolQuality).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [selected]);

  const filtered = etfList.filter(
    (e) => e.symbol.includes(filter) || e.name.includes(filter) || e.category.includes(filter)
  );

  const lastPrice = histData.length > 0 ? histData[histData.length - 1] : null;

  const scoreColor = (score: number) =>
    score >= 95 ? "var(--green)" : score >= 85 ? "var(--yellow)" : "var(--red)";

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "1.5rem", fontWeight: 700 }}>ETF 数据</h2>
        <button
          className={`btn ${showQuality ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setShowQuality(!showQuality)}
        >
          {showQuality ? "隐藏数据质量" : "查看数据质量"}
        </button>
      </div>

      {/* Data Quality Overview */}
      {showQuality && qualityOverview && (
        <div className="card" style={{ marginBottom: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 700 }}>数据质量报告</h3>
            <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                {qualityOverview.count} 只 ETF
              </span>
              <span style={{ fontSize: "1.25rem", fontWeight: 800, color: scoreColor(qualityOverview.average_score) }}>
                平均 {qualityOverview.average_score.toFixed(1)} 分
              </span>
            </div>
          </div>
          <div style={{ maxHeight: 300, overflow: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>数据条数</th>
                  <th>日期范围</th>
                  <th>缺口</th>
                  <th>零成交</th>
                  <th>异常价</th>
                  <th>NaN</th>
                  <th>质量分</th>
                </tr>
              </thead>
              <tbody>
                {qualityOverview.reports.map((r) => (
                  <tr key={r.symbol} onClick={() => { setSelected(r.symbol); setShowQuality(false); }} style={{ cursor: "pointer" }}>
                    <td style={{ fontFamily: "monospace", fontWeight: 600 }}>{r.symbol}</td>
                    <td>{r.total_rows.toLocaleString()}</td>
                    <td style={{ fontSize: "0.75rem" }}>{r.date_range}</td>
                    <td style={{ color: r.gap_count > 0 ? "var(--red)" : "var(--green)" }}>{r.gap_count}</td>
                    <td style={{ color: r.zero_volume_count > 0 ? "var(--yellow)" : "var(--green)" }}>{r.zero_volume_count}</td>
                    <td style={{ color: r.price_anomaly_count > 0 ? "var(--red)" : "var(--green)" }}>{r.price_anomaly_count}</td>
                    <td style={{ color: r.nan_count > 0 ? "var(--red)" : "var(--green)" }}>{r.nan_count}</td>
                    <td style={{ fontWeight: 700, color: scoreColor(r.quality_score) }}>{r.quality_score.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "1.5rem" }}>
        {/* Left: ETF List */}
        <div className="card" style={{ maxHeight: "80vh", overflow: "auto" }}>
          <input
            className="input"
            placeholder="搜索代码/名称/类别..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ marginBottom: "0.75rem" }}
          />
          <table className="data-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>类别</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((etf) => {
                const hasData = availableSymbols.has(etf.symbol);
                return (
                  <tr
                    key={etf.symbol}
                    onClick={() => hasData && setSelected(etf.symbol)}
                    style={{
                      cursor: hasData ? "pointer" : "default",
                      opacity: hasData ? 1 : 0.5,
                      background: selected === etf.symbol ? "rgba(59, 130, 246, 0.1)" : undefined,
                    }}
                  >
                    <td style={{ fontWeight: 600, fontFamily: "monospace" }}>{etf.symbol}</td>
                    <td>{etf.name}</td>
                    <td>
                      <span
                        style={{
                          fontSize: "0.7rem",
                          padding: "2px 6px",
                          borderRadius: 4,
                          background: "var(--bg-primary)",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {etf.category}
                      </span>
                    </td>
                    <td>
                      {hasData && (
                        <span style={{ color: "var(--green)", fontSize: "0.7rem" }}>有数据</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Right: Chart + Info */}
        <div>
          {selected && (
            <div style={{ marginBottom: "1rem", display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: "1.25rem", fontWeight: 700, fontFamily: "monospace" }}>
                {selected}
              </span>
              {lastPrice && (
                <>
                  <span style={{ fontSize: "1.5rem", fontWeight: 700 }}>{num(lastPrice.close, 3)}</span>
                  <Sparkline
                    data={histData.slice(-30).map((d) => d.close)}
                    width={100}
                    height={28}
                  />
                  <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                    {histData.length} 条记录 | {histData[0]?.date} ~ {lastPrice.date}
                  </span>
                </>
              )}
            </div>
          )}

          {loading ? (
            <div className="card" style={{ height: 400, display: "flex", alignItems: "center", justifyContent: "center" }}>
              加载中...
            </div>
          ) : (
            <PriceChart data={histData} />
          )}

          {/* Quick stats */}
          {lastPrice && histData.length > 1 && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginTop: "1rem" }}>
              <div className="card">
                <div className="metric-label">开盘</div>
                <div style={{ fontWeight: 600 }}>{num(lastPrice.open, 3)}</div>
              </div>
              <div className="card">
                <div className="metric-label">最高</div>
                <div style={{ fontWeight: 600, color: "var(--red)" }}>{num(lastPrice.high, 3)}</div>
              </div>
              <div className="card">
                <div className="metric-label">最低</div>
                <div style={{ fontWeight: 600, color: "var(--green)" }}>{num(lastPrice.low, 3)}</div>
              </div>
              <div className="card">
                <div className="metric-label">成交量</div>
                <div style={{ fontWeight: 600 }}>{lastPrice.volume.toLocaleString()}</div>
              </div>
            </div>
          )}
          {/* Per-symbol quality */}
          {symbolQuality && (
            <div className="card" style={{ marginTop: "1rem" }}>
              <h3 style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginBottom: "0.5rem" }}>数据质量</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "0.75rem" }}>
                <div>
                  <div className="metric-label">质量分</div>
                  <div style={{ fontSize: "1.25rem", fontWeight: 800, color: scoreColor(symbolQuality.quality_score) }}>
                    {symbolQuality.quality_score.toFixed(1)}
                  </div>
                </div>
                <div>
                  <div className="metric-label">数据条数</div>
                  <div style={{ fontWeight: 600 }}>{symbolQuality.total_rows.toLocaleString()}</div>
                </div>
                <div>
                  <div className="metric-label">缺口数</div>
                  <div style={{ fontWeight: 600, color: symbolQuality.gap_count > 0 ? "var(--red)" : "var(--green)" }}>
                    {symbolQuality.gap_count}
                  </div>
                </div>
                <div>
                  <div className="metric-label">零成交</div>
                  <div style={{ fontWeight: 600, color: symbolQuality.zero_volume_count > 0 ? "var(--yellow)" : "var(--green)" }}>
                    {symbolQuality.zero_volume_count}
                  </div>
                </div>
                <div>
                  <div className="metric-label">异常价</div>
                  <div style={{ fontWeight: 600, color: symbolQuality.price_anomaly_count > 0 ? "var(--red)" : "var(--green)" }}>
                    {symbolQuality.price_anomaly_count}
                  </div>
                </div>
              </div>
              {symbolQuality.gap_dates.length > 0 && (
                <div style={{ marginTop: 8, fontSize: "0.75rem", color: "var(--red)" }}>
                  缺口日期: {symbolQuality.gap_dates.join(", ")}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
