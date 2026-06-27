"use client";

import type { ReactNode } from "react";
import { usePortfolio } from "../context/PortfolioContext";
import { useMarket } from "../context/MarketContext";
import { fmtMoney, pnlColor } from "../lib/format";
import type { ConnectionStatus } from "../lib/types";

const STATUS_META: Record<
  ConnectionStatus,
  { color: string; label: string }
> = {
  connected: { color: "#3fb950", label: "LIVE" },
  reconnecting: { color: "#ecad0a", label: "RECONNECTING" },
  disconnected: { color: "#f85149", label: "OFFLINE" },
};

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[10px] uppercase tracking-wider text-[#8b949e]">
        {label}
      </span>
      <span className="font-mono text-sm">{children}</span>
    </div>
  );
}

export default function Header() {
  const { portfolio } = usePortfolio();
  const { connectionStatus } = useMarket();
  const status = STATUS_META[connectionStatus];

  return (
    <header className="flex items-center justify-between border-b border-terminal-border bg-terminal-panel px-4 py-2">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-bold tracking-tight text-accent-yellow">
          FinAlly
        </span>
        <span className="text-[10px] uppercase tracking-widest text-[#8b949e]">
          AI Trading Workstation
        </span>
      </div>

      <div className="flex items-center gap-6">
        <Stat label="Total Value">
          <span className="text-accent-blue">
            {fmtMoney(portfolio?.total_value)}
          </span>
        </Stat>
        <Stat label="Cash">{fmtMoney(portfolio?.cash)}</Stat>
        <Stat label="Realized P&L">
          <span className={pnlColor(portfolio?.realized_pnl ?? 0)}>
            {fmtMoney(portfolio?.realized_pnl)}
          </span>
        </Stat>
        <div className="flex items-center gap-2 pl-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: status.color, boxShadow: `0 0 6px ${status.color}` }}
          />
          <span className="text-[10px] uppercase tracking-wider text-[#8b949e]">
            {status.label}
          </span>
        </div>
      </div>
    </header>
  );
}
