"use client";

import { usePortfolio } from "../context/PortfolioContext";
import { fmtMoney, fmtPct, fmtQty, pnlColor } from "../lib/format";

export default function PositionsTable() {
  const { portfolio } = usePortfolio();
  const positions = portfolio?.positions ?? [];

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-terminal-border px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#8b949e]">
        Positions
      </div>
      <div className="flex-1 overflow-y-auto">
        {positions.length === 0 ? (
          <div className="p-4 text-sm text-[#8b949e]">No positions yet</div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-[#8b949e]">
                <th className="px-2 py-1 text-left">Ticker</th>
                <th className="px-2 py-1 text-right">Qty</th>
                <th className="px-2 py-1 text-right">Avg Cost</th>
                <th className="px-2 py-1 text-right">Price</th>
                <th className="px-2 py-1 text-right">Unreal. P&L</th>
                <th className="px-2 py-1 text-right">P&L %</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr
                  key={p.ticker}
                  className="border-t border-terminal-border/60 font-mono tabular-nums"
                >
                  <td className="px-2 py-1 text-left font-bold text-accent-yellow">
                    {p.ticker}
                  </td>
                  <td className="px-2 py-1 text-right">{fmtQty(p.quantity)}</td>
                  <td className="px-2 py-1 text-right">{fmtMoney(p.avg_cost)}</td>
                  <td className="px-2 py-1 text-right">
                    {fmtMoney(p.current_price)}
                  </td>
                  <td className={`px-2 py-1 text-right ${pnlColor(p.unrealized_pnl)}`}>
                    {fmtMoney(p.unrealized_pnl)}
                  </td>
                  <td className={`px-2 py-1 text-right ${pnlColor(p.pnl_pct)}`}>
                    {fmtPct(p.pnl_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
