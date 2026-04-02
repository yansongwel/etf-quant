"use client";

import { useEffect, useState } from "react";

interface RefreshTimerProps {
  intervalSec: number;
  onRefresh: () => void;
  loading?: boolean;
}

/**
 * Circular countdown timer showing seconds until next auto-refresh.
 * Click to refresh immediately.
 */
export default function RefreshTimer({ intervalSec, onRefresh, loading }: RefreshTimerProps) {
  const [remaining, setRemaining] = useState(intervalSec);

  useEffect(() => {
    setRemaining(intervalSec);
    const timer = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          onRefresh();
          return intervalSec;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [intervalSec, onRefresh]);

  // Reset after manual refresh
  useEffect(() => {
    if (loading) setRemaining(intervalSec);
  }, [loading, intervalSec]);

  const progress = remaining / intervalSec;
  const radius = 10;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * progress;

  return (
    <button
      onClick={() => { onRefresh(); setRemaining(intervalSec); }}
      disabled={loading}
      title={loading ? "刷新中..." : `${remaining}秒后自动刷新 · 点击立即刷新`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        borderRadius: 6,
        border: "1px solid var(--border)",
        background: "transparent",
        color: "var(--text-secondary)",
        fontSize: "0.7rem",
        cursor: loading ? "wait" : "pointer",
        transition: "all 0.15s",
        whiteSpace: "nowrap",
      }}
    >
      <svg width={24} height={24} viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
        {/* Background circle */}
        <circle cx={12} cy={12} r={radius} fill="none" stroke="var(--border)" strokeWidth={2} />
        {/* Progress arc */}
        <circle
          cx={12} cy={12} r={radius}
          fill="none"
          stroke={loading ? "var(--text-tertiary)" : "var(--accent, #4f8ff7)"}
          strokeWidth={2}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - dashOffset}
          transform="rotate(-90 12 12)"
          style={{ transition: "stroke-dashoffset 0.3s" }}
        />
        {/* Center text */}
        <text x={12} y={12.5} textAnchor="middle" dominantBaseline="middle"
          fontSize={loading ? 7 : 8} fontWeight={700}
          fill={loading ? "var(--text-tertiary)" : "var(--text-secondary)"}>
          {loading ? "..." : remaining}
        </text>
      </svg>
      <span>{loading ? "刷新中" : "自动刷新"}</span>
    </button>
  );
}
