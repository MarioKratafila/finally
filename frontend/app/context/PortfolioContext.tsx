"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getPortfolio, getPortfolioHistory } from "../lib/api";
import type { HistoryPoint, Portfolio } from "../lib/types";

interface PortfolioContextValue {
  portfolio: Portfolio | null;
  history: HistoryPoint[];
  refresh: () => Promise<void>;
}

const PortfolioContext = createContext<PortfolioContextValue | null>(null);

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);

  const refresh = useCallback(async () => {
    try {
      setPortfolio(await getPortfolio());
    } catch {
      // backend may not be ready; keep last good state
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await getPortfolioHistory());
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    refreshHistory();
    const id = setInterval(refreshHistory, 30000);
    return () => clearInterval(id);
  }, [refreshHistory]);

  return (
    <PortfolioContext.Provider value={{ portfolio, history, refresh }}>
      {children}
    </PortfolioContext.Provider>
  );
}

export function usePortfolio(): PortfolioContextValue {
  const ctx = useContext(PortfolioContext);
  if (!ctx)
    throw new Error("usePortfolio must be used within PortfolioProvider");
  return ctx;
}
