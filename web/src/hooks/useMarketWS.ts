/**
 * WebSocket hook for real-time market data.
 *
 * Connects to the FastAPI WebSocket endpoint and provides
 * live market updates to any component that needs them.
 *
 * During trading hours: updates every ~10 seconds
 * After hours: updates every ~60 seconds
 */

import { useEffect, useRef, useState, useCallback } from "react";

export interface MarketQuote {
  symbol: string;
  name: string;
  price: number;
  change_pct: number;
}

export interface MarketUpdate {
  type: "market_update" | "error";
  market_open?: boolean;
  timestamp?: string;
  quotes?: MarketQuote[];
  total_etfs?: number;
  signal_summary?: { buy: number; hold: number; sell: number };
  message?: string;
}

const WS_URL =
  typeof window !== "undefined"
    ? `ws://${window.location.hostname}:8000/ws/market`
    : "";

export function useMarketWS(): {
  data: MarketUpdate | null;
  connected: boolean;
} {
  const [data, setData] = useState<MarketUpdate | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!WS_URL || wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const msg: MarketUpdate = JSON.parse(event.data);
          setData(msg);
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        // Reconnect after 5 seconds
        reconnectTimer.current = setTimeout(connect, 5000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // WebSocket not available (SSR or blocked)
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { data, connected };
}
