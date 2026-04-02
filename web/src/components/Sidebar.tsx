"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

interface NavGroup {
  label: string;
  items: { href: string; label: string; icon: string; badge?: string }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "交易决策",
    items: [
      { href: "/", label: "今日看板", icon: "📊" },
      { href: "/signals", label: "交易信号", icon: "🎯", badge: "核心" },
      { href: "/explorer", label: "信号回验", icon: "🔬" },
      { href: "/sector", label: "板块轮动", icon: "🔄" },
      { href: "/recommend", label: "策略推荐", icon: "💡" },
      { href: "/sentiment", label: "市场舆情", icon: "📰" },
    ],
  },
  {
    label: "持仓管理",
    items: [
      { href: "/portfolio", label: "我的持仓", icon: "💼" },
      { href: "/risk", label: "风险评估", icon: "🛡️" },
    ],
  },
  {
    label: "研究工具",
    items: [
      { href: "/flow", label: "大单异动", icon: "🔍" },
      { href: "/backtest", label: "策略回测", icon: "⚡" },
      { href: "/factors", label: "因子分析", icon: "🧮" },
      { href: "/data", label: "数据中心", icon: "📈" },
    ],
  },
];

const REGIME_STYLES: Record<string, { color: string; bg: string }> = {
  bull: { color: "#10b981", bg: "rgba(16, 185, 129, 0.08)" },
  bear: { color: "#ef4444", bg: "rgba(239, 68, 68, 0.08)" },
  range: { color: "#f59e0b", bg: "rgba(245, 158, 11, 0.08)" },
};

const REGIME_ICONS: Record<string, string> = {
  bull: "📈",
  bear: "📉",
  range: "↔️",
};

interface RegimeData {
  regime: string;
  label: string;
  indicators: { momentum_20d?: number };
}

export default function Sidebar() {
  const pathname = usePathname();
  const [regime, setRegime] = useState<RegimeData | null>(null);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [dataDate, setDataDate] = useState<string | null>(null);
  const [serverTimeCst, setServerTimeCst] = useState<string | null>(null);
  const [etfCount, setEtfCount] = useState<number>(0);
  const [benchmark, setBenchmark] = useState<{ price: number; change_pct: number } | null>(null);
  const [marketStatus, setMarketStatus] = useState<string | null>(null);
  const [platformVersion, setPlatformVersion] = useState<string>("");
  const [signalVersion, setSignalVersion] = useState<string>("");

  useEffect(() => {
    fetch("/market/regime")
      .then((r) => r.json())
      .then(setRegime)
      .catch(() => {});

    fetch("/market/realtime")
      .then((r) => r.json())
      .then((d) => {
        const hs300 = d?.quotes?.find((q: { symbol: string }) => q.symbol === "510300");
        if (hs300) setBenchmark({ price: hs300.price, change_pct: hs300.change_pct });
      })
      .catch(() => {});

    const checkHealth = () => {
      fetch("/health")
        .then((r) => r.json())
        .then((d) => {
          setApiOnline(d.status === "ok");
          if (d.data_date) setDataDate(d.data_date);
          if (d.server_time_cst) setServerTimeCst(d.server_time_cst);
          if (d.etf_count) setEtfCount(d.etf_count);
          if (d.market_status) setMarketStatus(d.market_status);
          if (d.platform_version) setPlatformVersion(d.platform_version);
          if (d.signal_version) setSignalVersion(d.signal_version);
        })
        .catch(() => setApiOnline(false));
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30_000);
    return () => clearInterval(interval);
  }, []);

  const rs = regime ? REGIME_STYLES[regime.regime] || { color: "#94a3b8", bg: "rgba(148,163,184,0.08)" } : null;

  return (
    <aside
      style={{
        width: 220,
        minHeight: "100vh",
        background: "var(--bg-secondary)",
        borderRight: "1px solid var(--border)",
        padding: "1.25rem 0",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Logo */}
      <div style={{ padding: "0 1.25rem", marginBottom: "1.25rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "linear-gradient(135deg, #4f8ff7, #8b5cf6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "0.9rem",
              fontWeight: 800,
              color: "white",
            }}
          >
            EQ
          </div>
          <div>
            <div style={{ fontSize: "1rem", fontWeight: 700, letterSpacing: "-0.02em" }}>ETF Quant</div>
            <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", letterSpacing: "0.05em" }}>
              量化投研平台
            </div>
          </div>
        </div>
      </div>

      {/* Market regime */}
      {regime && rs && (
        <div
          style={{
            margin: "0 0.75rem 1rem",
            padding: "0.65rem 0.85rem",
            borderRadius: 10,
            background: rs.bg,
            border: `1px solid ${rs.color}25`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
            <span style={{ fontSize: "0.85rem" }}>{REGIME_ICONS[regime.regime] || "📊"}</span>
            <span style={{ fontSize: "0.8rem", fontWeight: 700, color: rs.color }}>
              {regime.label}
            </span>
          </div>
          {benchmark && (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: "0.7rem", marginBottom: 2 }}>
              <span style={{ color: "var(--text-secondary)" }}>沪深300</span>
              <span>
                <span className="mono" style={{ fontWeight: 600, marginRight: 4 }}>¥{benchmark.price.toFixed(3)}</span>
                <span style={{ color: benchmark.change_pct > 0 ? "var(--green)" : benchmark.change_pct < 0 ? "var(--red)" : "var(--text-secondary)", fontWeight: 600 }}>
                  {benchmark.change_pct > 0 ? "+" : ""}{benchmark.change_pct.toFixed(2)}%
                </span>
              </span>
            </div>
          )}
          {regime.indicators?.momentum_20d !== undefined && (
            <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>
              20日动量:{" "}
              <span style={{ color: regime.indicators.momentum_20d > 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                {regime.indicators.momentum_20d > 0 ? "+" : ""}
                {regime.indicators.momentum_20d}%
              </span>
            </div>
          )}
        </div>
      )}

      {/* Grouped navigation */}
      <nav style={{ flex: 1, padding: "0 0.5rem" }}>
        {NAV_GROUPS.map((group, gi) => (
          <div key={group.label}>
            {/* Group label */}
            <div
              style={{
                fontSize: "0.65rem",
                fontWeight: 600,
                color: "var(--text-tertiary)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                padding: "0.5rem 0.75rem 0.25rem",
                marginTop: gi > 0 ? "0.5rem" : 0,
              }}
            >
              {group.label}
            </div>
            {group.items.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.65rem",
                    padding: "0.5rem 0.75rem",
                    margin: "1px 0",
                    fontSize: "0.85rem",
                    color: active ? "var(--text-primary)" : "var(--text-secondary)",
                    background: active ? "var(--accent-glow)" : "transparent",
                    borderRadius: 8,
                    textDecoration: "none",
                    transition: "all 0.15s",
                    fontWeight: active ? 600 : 400,
                  }}
                >
                  <span style={{ fontSize: "0.85rem", opacity: active ? 1 : 0.7 }}>{item.icon}</span>
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {item.badge && (
                    <span
                      style={{
                        fontSize: "0.6rem",
                        fontWeight: 700,
                        padding: "1px 5px",
                        borderRadius: 4,
                        background: "rgba(79, 143, 247, 0.15)",
                        color: "var(--accent)",
                      }}
                    >
                      {item.badge}
                    </span>
                  )}
                  {active && (
                    <div
                      style={{
                        width: 3,
                        height: 14,
                        borderRadius: 2,
                        background: "var(--accent)",
                        flexShrink: 0,
                      }}
                    />
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer status */}
      <div
        style={{
          padding: "0.75rem 1.25rem",
          borderTop: "1px solid var(--border)",
          marginTop: "0.5rem",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: "0.7rem",
            color: "var(--text-secondary)",
            marginBottom: 4,
          }}
        >
          <span
            className={
              apiOnline === null ? "dot dot-gray" : apiOnline ? "dot dot-green" : "dot dot-red"
            }
          />
          {apiOnline === null ? "检测中..." : apiOnline ? "API 在线" : "API 离线"}
          {marketStatus && (
            <span style={{ marginLeft: 6, color: marketStatus === "trading" ? "var(--green)" : marketStatus === "lunch" ? "var(--yellow, #f59e0b)" : "var(--text-tertiary)" }}>
              · {marketStatus === "trading" ? "交易中" : marketStatus === "lunch" ? "午休" : "已收盘"}
            </span>
          )}
        </div>
        {dataDate && (() => {
          const daysSince = Math.floor((Date.now() - new Date(dataDate).getTime()) / 86400000);
          const isStale = daysSince > 2;
          return (
            <div style={{ fontSize: "0.65rem", color: isStale ? "var(--yellow, #f59e0b)" : "var(--text-tertiary)", marginBottom: 2 }}>
              数据截止: {dataDate}{isStale ? ` (${daysSince}天前)` : ""}
            </div>
          );
        })()}
        {serverTimeCst && (
          <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", marginBottom: 2 }}>
            北京时间: {serverTimeCst}
          </div>
        )}
        <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", marginBottom: 2 }}>
          v{platformVersion || "3.6"}{etfCount > 0 ? ` · ${etfCount} ETFs` : ""}
        </div>
        {signalVersion && (
          <div style={{ fontSize: "0.6rem", color: "var(--accent, #4f8ff7)", marginBottom: 6, fontFamily: "monospace" }}>
            Signal V{signalVersion}
          </div>
        )}
        <button
          onClick={() => {
            localStorage.removeItem("etf_quant_logged_in");
            localStorage.removeItem("etf_quant_user");
            window.location.href = "/login";
          }}
          style={{
            background: "none",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "4px 10px",
            fontSize: "0.65rem",
            color: "var(--text-tertiary)",
            cursor: "pointer",
            transition: "all 0.15s",
            width: "100%",
          }}
        >
          退出登录
        </button>
      </div>
    </aside>
  );
}
