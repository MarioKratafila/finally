"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { ConnectionStatus, PriceEvent } from "../lib/types";

const MAX_SPARKLINE_POINTS = 120;

interface MarketContextValue {
  prices: Map<string, PriceEvent>;
  sparklines: Map<string, number[]>;
  connectionStatus: ConnectionStatus;
}

const MarketContext = createContext<MarketContextValue | null>(null);

export function MarketProvider({ children }: { children: ReactNode }) {
  const [prices, setPrices] = useState<Map<string, PriceEvent>>(new Map());
  const [sparklines, setSparklines] = useState<Map<string, number[]>>(
    new Map()
  );
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("reconnecting");

  useEffect(() => {
    const source = new EventSource("/api/stream/prices");

    source.onopen = () => setConnectionStatus("connected");

    source.onmessage = (event) => {
      let data: PriceEvent;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!data?.ticker) return;

      setPrices((prev) => {
        const next = new Map(prev);
        next.set(data.ticker, data);
        return next;
      });
      setSparklines((prev) => {
        const next = new Map(prev);
        const series = next.get(data.ticker) ?? [];
        const updated = [...series, data.price];
        if (updated.length > MAX_SPARKLINE_POINTS) updated.shift();
        next.set(data.ticker, updated);
        return next;
      });
    };

    source.onerror = () => {
      setConnectionStatus(
        source.readyState === EventSource.CLOSED
          ? "disconnected"
          : "reconnecting"
      );
    };

    return () => source.close();
  }, []);

  return (
    <MarketContext.Provider value={{ prices, sparklines, connectionStatus }}>
      {children}
    </MarketContext.Provider>
  );
}

export function useMarket(): MarketContextValue {
  const ctx = useContext(MarketContext);
  if (!ctx) throw new Error("useMarket must be used within MarketProvider");
  return ctx;
}
