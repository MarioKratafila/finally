"use client";

import { useState, type ReactNode } from "react";
import { MarketProvider } from "./context/MarketContext";
import { PortfolioProvider } from "./context/PortfolioContext";
import Header from "./components/Header";
import WatchlistPanel from "./components/WatchlistPanel";
import MainChart from "./components/MainChart";
import PortfolioHeatmap from "./components/PortfolioHeatmap";
import PnLChart from "./components/PnLChart";
import PositionsTable from "./components/PositionsTable";
import TradeBar from "./components/TradeBar";
import ChatPanel from "./components/ChatPanel";

function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden rounded border border-terminal-border bg-terminal-panel ${className}`}
    >
      {children}
    </div>
  );
}

export default function Home() {
  const [selected, setSelected] = useState<string | null>("AAPL");
  const [tradeTicker, setTradeTicker] = useState("AAPL");
  const [chatCollapsed, setChatCollapsed] = useState(false);

  const selectTicker = (ticker: string) => {
    setSelected(ticker);
    setTradeTicker(ticker);
  };

  return (
    <MarketProvider>
      <PortfolioProvider>
        <div className="flex h-screen flex-col bg-terminal-bg">
          <Header />

          <div className="flex min-h-0 flex-1">
            {/* Left + center work area */}
            <div className="flex min-w-0 flex-1 flex-col gap-2 p-2">
              <div className="flex min-h-0 flex-1 gap-2">
                <Panel className="w-72 shrink-0">
                  <WatchlistPanel selected={selected} onSelect={selectTicker} />
                </Panel>
                <Panel className="min-w-0 flex-1">
                  <MainChart ticker={selected} />
                </Panel>
              </div>

              <div className="flex h-64 shrink-0 gap-2">
                <Panel className="min-w-0 flex-1">
                  <PortfolioHeatmap />
                </Panel>
                <Panel className="min-w-0 flex-1">
                  <PnLChart />
                </Panel>
              </div>

              <Panel className="h-48 shrink-0">
                <PositionsTable />
              </Panel>

              <Panel className="shrink-0">
                <TradeBar
                  ticker={tradeTicker}
                  onTickerChange={setTradeTicker}
                />
              </Panel>
            </div>

            {/* Right chat sidebar */}
            <div
              className={`shrink-0 transition-all ${
                chatCollapsed ? "w-10" : "w-80"
              }`}
            >
              <ChatPanel
                collapsed={chatCollapsed}
                onToggle={() => setChatCollapsed((c) => !c)}
              />
            </div>
          </div>
        </div>
      </PortfolioProvider>
    </MarketProvider>
  );
}
