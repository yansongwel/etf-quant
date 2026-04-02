"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

const MAIN_TABS = [
  { href: "/", label: "看板", icon: "📊" },
  { href: "/signals", label: "信号", icon: "🎯" },
  { href: "/sector", label: "板块", icon: "🔄" },
  { href: "/portfolio", label: "持仓", icon: "💼" },
];

const MORE_ITEMS = [
  { href: "/recommend", label: "策略推荐", icon: "💡" },
  { href: "/risk", label: "风险评估", icon: "🛡️" },
  { href: "/flow", label: "大单异动", icon: "🔍" },
  { href: "/explorer", label: "信号回验", icon: "🔬" },
  { href: "/sentiment", label: "市场舆情", icon: "📰" },
  { href: "/backtest", label: "策略回测", icon: "⚡" },
  { href: "/factors", label: "因子分析", icon: "🧮" },
  { href: "/data", label: "数据中心", icon: "📈" },
];

export default function MobileNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [showMore, setShowMore] = useState(false);

  const isMoreActive = MORE_ITEMS.some((item) => pathname === item.href);

  return (
    <>
      {/* More menu overlay */}
      {showMore && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 998,
            background: "rgba(0,0,0,0.5)",
          }}
          onClick={() => setShowMore(false)}
        />
      )}
      {showMore && (
        <div
          style={{
            position: "fixed",
            bottom: 56,
            left: 0,
            right: 0,
            zIndex: 999,
            background: "var(--bg-secondary)",
            borderTop: "1px solid var(--border)",
            borderRadius: "16px 16px 0 0",
            padding: "12px 8px 8px",
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 4,
          }}
        >
          {MORE_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setShowMore(false)}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 2,
                  padding: "10px 4px",
                  borderRadius: 10,
                  background: active ? "var(--accent-glow)" : "transparent",
                  textDecoration: "none",
                  color: active ? "var(--accent)" : "var(--text-secondary)",
                  fontSize: "0.72rem",
                  fontWeight: active ? 700 : 500,
                  transition: "all 0.15s",
                }}
              >
                <span style={{ fontSize: "1.2rem" }}>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      )}

      {/* Bottom tab bar */}
      <nav
        style={{
          position: "fixed",
          bottom: 0,
          left: 0,
          right: 0,
          zIndex: 1000,
          height: 56,
          background: "var(--bg-secondary)",
          borderTop: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-around",
          paddingBottom: "env(safe-area-inset-bottom, 0px)",
        }}
      >
        {MAIN_TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 1,
                padding: "4px 12px",
                textDecoration: "none",
                color: active ? "var(--accent)" : "var(--text-tertiary)",
                fontSize: "0.65rem",
                fontWeight: active ? 700 : 500,
                transition: "color 0.15s",
              }}
            >
              <span style={{ fontSize: "1.1rem", opacity: active ? 1 : 0.6 }}>{tab.icon}</span>
              <span>{tab.label}</span>
              {active && (
                <span style={{
                  width: 4, height: 4, borderRadius: "50%",
                  background: "var(--accent)", marginTop: -1,
                }} />
              )}
            </Link>
          );
        })}

        {/* More button */}
        <button
          onClick={() => setShowMore(!showMore)}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 1,
            padding: "4px 12px",
            background: "none",
            border: "none",
            color: showMore || isMoreActive ? "var(--accent)" : "var(--text-tertiary)",
            fontSize: "0.65rem",
            fontWeight: showMore || isMoreActive ? 700 : 500,
            cursor: "pointer",
          }}
        >
          <span style={{ fontSize: "1.1rem", opacity: showMore || isMoreActive ? 1 : 0.6 }}>⋯</span>
          <span>更多</span>
        </button>
      </nav>
    </>
  );
}
