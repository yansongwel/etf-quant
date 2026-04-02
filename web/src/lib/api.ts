/**
 * API client for the ETF Quant backend.
 * Uses Next.js rewrites to proxy /api/* to the FastAPI backend.
 */

const API_BASE = "";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export interface ETFInfo {
  symbol: string;
  name: string;
  category: string;
}

export interface HistDataPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface HistResponse {
  symbol: string;
  count: number;
  data: HistDataPoint[];
}

export interface FactorDataPoint {
  date: string;
  [key: string]: string | number | null;
}

export interface FactorResponse {
  symbol: string;
  category: string;
  factors: string[];
  count: number;
  data: FactorDataPoint[];
}

export interface BacktestMetrics {
  total_return: number;
  annualized_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  calmar_ratio: number;
  win_rate: number;
  total_trades: number;
}

export interface EquityPoint {
  date: string;
  value: number;
}

export interface TradeRecord {
  date: string;
  signal_date: string;
  symbol: string;
  side: "buy" | "sell";
  price: number;
  shares: number;
  commission: number;
}

export interface BacktestResponse {
  metrics: BacktestMetrics;
  equity_curve: { count: number; data: EquityPoint[] };
  trades: { count: number; data: TradeRecord[] };
  warnings: string[];
}

export interface RotationParams {
  symbols: string[];
  lookback: number;
  top_k: number;
  rebalance_days: number;
  initial_cash: number;
  commission_rate: number;
  slippage: number;
}

export interface HealthResponse {
  status: string;
  services: { redis: string };
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export interface SignalData {
  symbol: string;
  name?: string;
  direction: string;
  strength: number;
  current_price: number;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  score: number;
  reason: string;
  tier: "action" | "watch" | "reference" | "noise";
}

export interface SignalsResponse {
  count: number;
  signals: SignalData[];
  summary: Record<string, number>;
  tiers?: Record<string, number>;
  generated_at?: string;
}

export interface PositionData {
  symbol: string;
  name?: string;
  direction: string;
  score: number;
  current_price: number;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  shares: number;
  buy_amount: number;
  expected_gain: number;
  max_loss: number;
  risk_reward: number;
  reason: string;
}

export interface PositionsResponse {
  capital: number;
  invested: number;
  remaining: number;
  positions: PositionData[];
  disclaimer: string;
}

export interface RecommendationData {
  strategy_name: string;
  strategy_id: string;
  rank: number;
  recommendation: string;
  metrics: Record<string, number>;
}

export interface RecommendResponse {
  capital: number;
  count: number;
  recommendations: RecommendationData[];
  disclaimer: string;
}

// --- Data Quality ---

export interface QualityReport {
  symbol: string;
  total_rows: number;
  date_range: string;
  trading_days: number;
  gap_count: number;
  gap_dates: string[];
  zero_volume_count: number;
  price_anomaly_count: number;
  nan_count: number;
  quality_score: number;
}

export interface QualityOverview {
  count: number;
  average_score: number;
  reports: QualityReport[];
}

// --- Sector Rotation ---

export interface SectorData {
  sector_name: string;
  phase: string;
  phase_label: string;
  etf_symbols: string[];
  best_etf: string;
  best_etf_name: string;
  momentum_20d: number;
  momentum_5d: number;
  momentum_acceleration: number;
  rsi: number;
  ma_ratio: number;
  volatility: number;
  score: number;
  risk_level: string;
  action: string;
  allocation_pct: number;
}

export interface SectorRotationResponse {
  count: number;
  sectors: SectorData[];
  generated_at?: string;
}

// --- Signal Detail ---

export interface SignalDetail {
  symbol: string;
  direction: string;
  strength: number;
  current_price: number;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  position_pct: number;
  reason: string;
  factors: Record<string, number>;
  score: number;
}

// --- Factor Compare ---

export interface FactorCompareItem {
  symbol: string;
  [key: string]: string | number | null;
}

export interface FactorCompareResponse {
  category: string;
  factors: string[];
  count: number;
  data: FactorCompareItem[];
  missing: string[];
}

// --- Backtest Strategies ---

export interface StrategyInfoItem {
  id: string;
  name: string;
  description: string;
  endpoint: string;
}

// --- Signal Trend ---

export interface SignalTrendPoint {
  date: string;
  score: number;
  direction: string;
  close: number;
}

export interface SignalTrendResponse {
  symbol: string;
  count: number;
  trend: SignalTrendPoint[];
  generated_at: string;
}

// --- Sector Groups ---

export interface SectorGroup {
  sector: string;
  phase: string;
  phase_label: string;
  etfs: { symbol: string; name: string }[];
  best_etf: string;
}

export const api = {
  health: () => fetchJSON<HealthResponse>("/health"),
  etfList: () => fetchJSON<ETFInfo[]>("/etf/list"),
  symbols: () => fetchJSON<{ symbols: string[]; count: number }>("/api/data/symbols"),
  hist: (symbol: string, limit = 500) =>
    fetchJSON<HistResponse>(`/api/data/hist/${symbol}?limit=${limit}`),
  dataQuality: () => fetchJSON<QualityOverview>("/api/data/quality"),
  dataQualitySymbol: (symbol: string) =>
    fetchJSON<QualityReport>(`/api/data/quality/${symbol}`),
  factors: (symbol: string, category = "momentum", tail = 60) =>
    fetchJSON<FactorResponse>(`/api/factors/${symbol}?category=${category}&tail=${tail}`),
  factorsCompare: (symbols: string[], category = "momentum") =>
    fetchJSON<FactorCompareResponse>("/api/factors/compare", {
      method: "POST",
      body: JSON.stringify({ symbols, category }),
    }),
  backtestStrategies: () => fetchJSON<StrategyInfoItem[]>("/api/backtest/strategies"),
  backtestRotation: (params: RotationParams) =>
    fetchJSON<BacktestResponse>("/api/backtest/rotation", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  signals: (symbols = "") =>
    fetchJSON<SignalsResponse>(`/api/signals/current?symbols=${symbols}`),
  signalDetail: (symbol: string) =>
    fetchJSON<SignalDetail>(`/api/signals/detail/${symbol}`),
  positions: (capital: number, maxPositions = 5) =>
    fetchJSON<PositionsResponse>("/api/signals/positions", {
      method: "POST",
      body: JSON.stringify({ capital, max_positions: maxPositions }),
    }),
  recommend: (capital: number, maxResults = 5) =>
    fetchJSON<RecommendResponse>("/api/signals/recommend", {
      method: "POST",
      body: JSON.stringify({ capital, max_results: maxResults }),
    }),
  signalRecord: () =>
    fetchJSON<{ recorded: number }>("/api/signals/record", {
      method: "POST",
      headers: API_KEY ? { "X-API-Key": API_KEY } : undefined,
    }),
  signalAccuracy: (days = 30) =>
    fetchJSON<{ overall_accuracy: number; records_checked: number; total_signals: number; by_direction: Record<string, { accuracy: number; total: number; avg_return: number }> }>(
      `/api/signals/accuracy?days=${days}`
    ),
  signalAlerts: () =>
    fetchJSON<{ alerts: Array<{ symbol: string; alert_type: string; current_price: number; trigger_price: number; message: string }> }>(
      "/api/signals/alerts"
    ),
  signalTrend: (symbol: string, days = 60) =>
    fetchJSON<SignalTrendResponse>(`/api/signals/trend/${symbol}?days=${days}`),
  sectorGroups: () =>
    fetchJSON<{ count: number; groups: SectorGroup[] }>("/api/sector/groups"),
  sectorRotation: () => fetchJSON<SectorRotationResponse>("/api/sector/rotation"),
  sectorPlan: (capital: number, riskAppetite = "aggressive", maxSectors = 5) =>
    fetchJSON<unknown>("/api/sector/plan", {
      method: "POST",
      body: JSON.stringify({ capital, risk_appetite: riskAppetite, max_sectors: maxSectors }),
    }),
  recommendProven: (capital: number) =>
    fetchJSON<unknown>("/api/recommend/proven", {
      method: "POST",
      body: JSON.stringify({ capital }),
    }),
};
