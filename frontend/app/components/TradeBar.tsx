"use client";

import { useState } from "react";
import { usePortfolio } from "../context/PortfolioContext";
import { executeTrade } from "../lib/api";
import type { TradeSide } from "../lib/types";

interface TradeBarProps {
  ticker: string;
  onTickerChange: (ticker: string) => void;
}

export default function TradeBar({ ticker, onTickerChange }: TradeBarProps) {
  const { refresh } = usePortfolio();
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(
    null
  );

  const submit = async (side: TradeSide) => {
    const quantity = Number(qty);
    const symbol = ticker.trim().toUpperCase();
    if (!symbol || !quantity || quantity <= 0) {
      setFeedback({ ok: false, text: "Enter a ticker and positive quantity" });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      await executeTrade({ ticker: symbol, quantity, side });
      setFeedback({
        ok: true,
        text: `${side.toUpperCase()} ${quantity} ${symbol} filled`,
      });
      setQty("");
      await refresh();
    } catch (err) {
      setFeedback({
        ok: false,
        text: err instanceof Error ? err.message : "Trade failed",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2 border-t border-terminal-border bg-terminal-panel px-3 py-2">
      <span className="text-[10px] uppercase tracking-wider text-[#8b949e]">
        Trade
      </span>
      <input
        value={ticker}
        onChange={(e) => onTickerChange(e.target.value.toUpperCase())}
        placeholder="Ticker"
        className="w-24 rounded border border-terminal-border bg-terminal-bg px-2 py-1 font-mono text-sm uppercase outline-none focus:border-accent-blue"
      />
      <input
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        placeholder="Qty"
        type="number"
        min="0"
        step="any"
        className="w-24 rounded border border-terminal-border bg-terminal-bg px-2 py-1 font-mono text-sm outline-none focus:border-accent-blue"
      />
      <button
        onClick={() => submit("buy")}
        disabled={busy}
        className="rounded bg-accent-purple px-4 py-1 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
      >
        BUY
      </button>
      <button
        onClick={() => submit("sell")}
        disabled={busy}
        className="rounded bg-loss px-4 py-1 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
      >
        SELL
      </button>
      {feedback && (
        <span
          className={`ml-2 text-xs ${feedback.ok ? "text-gain" : "text-loss"}`}
        >
          {feedback.text}
        </span>
      )}
    </div>
  );
}
