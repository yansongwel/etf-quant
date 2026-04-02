/**
 * Formatting utilities for the dashboard.
 */

export function pct(value: number, decimals = 2): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function money(value: number): string {
  if (value >= 1_000_000) return `¥${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `¥${(value / 1_000).toFixed(1)}K`;
  return `¥${value.toFixed(2)}`;
}

export function num(value: number, decimals = 4): string {
  return value.toFixed(decimals);
}

export function shortDate(dateStr: string): string {
  return dateStr.slice(5); // "2024-03-15" → "03-15"
}

export function signClass(value: number): string {
  if (value > 0) return "metric-positive";
  if (value < 0) return "metric-negative";
  return "";
}

/**
 * Format P&L amount with clear gain/loss label.
 * +¥6,441 盈利  or  -¥6,441 亏损
 */
export function pnl(value: number): string {
  const abs = Math.abs(value);
  const formatted = abs >= 10000
    ? `¥${(abs / 10000).toFixed(2)}万`
    : `¥${abs.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
  if (value > 0) return `+${formatted} 盈利`;
  if (value < 0) return `-${formatted} 亏损`;
  return `${formatted} 持平`;
}

/**
 * Format P&L percentage with clear label.
 * +5.2% 盈利  or  -3.1% 亏损
 */
export function pnlPct(value: number): string {
  if (value > 0) return `+${value.toFixed(2)}% 盈利`;
  if (value < 0) return `${value.toFixed(2)}% 亏损`;
  return `0.00% 持平`;
}

/**
 * Get current Beijing time string (CST, UTC+8).
 * A-stock market always uses Beijing time regardless of browser timezone.
 */
export function nowCST(): string {
  const now = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
  const cst = new Date(utcMs + 8 * 3600000);
  return cst.toLocaleTimeString("zh-CN", { hour12: false });
}
