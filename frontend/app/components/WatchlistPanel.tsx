"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMarket } from "../context/MarketContext";
import { addWatchlistTicker, getWatchlist, removeWatchlistTicker } from "../lib/api";
import { fmtPct } from "../lib/format";
import type { PriceEvent } from "../lib/types";
import Sparkline from "./Sparkline";

interface WatchlistPanelProps {
  selected: string | null;
  onSelect: (ticker: string) => void;
}

function PriceCell({ price }: { price: PriceEvent }) {
  const flashRef = useRef<HTMLSpanElement>(null);
  const prevRef = useRef<number>(price.price);

  useEffect(() => {
    const el = flashRef.current;
    if (!el) return;
    if (price.price === prevRef.current) return;
    const cls =
      price.price > prevRef.current ? "price-flash-up" : "price-flash-down";
    el.classList.remove("price-flash-up", "price-flash-down");
    void el.offsetWidth; // restart animation
    el.classList.add(cls);
    prevRef.current = price.price;
  }, [price.price]);

  return (
    <span ref={flashRef} className="rounded px-1 font-mono tabular-nums">
      {price.price.toFixed(2)}
    </span>
  );
}

export default function WatchlistPanel({
  selected,
  onSelect,
}: WatchlistPanelProps) {
  const { prices, sparklines } = useMarket();
  const [tickers, setTickers] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadWatchlist = async () => {
    try {
      const list = await getWatchlist();
      setTickers(list.map((w) => w.ticker));
    } catch {
      // backend not ready
    }
  };

  useEffect(() => {
    loadWatchlist();
    const id = setInterval(loadWatchlist, 10000);
    return () => clearInterval(id);
  }, []);

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    const ticker = input.trim().toUpperCase();
    if (!ticker) return;
    setError(null);
    try {
      await addWatchlistTicker(ticker);
      setInput("");
      await loadWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add ticker");
    }
  };

  const handleRemove = async (ticker: string) => {
    setError(null);
    try {
      await removeWatchlistTicker(ticker);
      await loadWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove ticker");
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-terminal-border px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#8b949e]">
        Watchlist
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full border-collapse text-sm">
          <tbody>
            {tickers.map((ticker) => {
              const price = prices.get(ticker);
              const spark = sparklines.get(ticker) ?? [];
              const isSelected = ticker === selected;
              const changePct = price?.change_pct ?? 0;
              const up = changePct >= 0;
              return (
                <tr
                  key={ticker}
                  onClick={() => onSelect(ticker)}
                  className={`group cursor-pointer border-b border-terminal-border/60 hover:bg-white/5 ${
                    isSelected ? "bg-accent-blue/10" : ""
                  }`}
                >
                  <td className="py-1.5 pl-3 pr-1">
                    <span className="font-mono font-bold text-accent-yellow">
                      {ticker}
                    </span>
                  </td>
                  <td className="px-1 text-right">
                    {price ? (
                      <PriceCell price={price} />
                    ) : (
                      <span className="font-mono text-[#8b949e]">—</span>
                    )}
                  </td>
                  <td
                    className={`px-1 text-right font-mono tabular-nums ${
                      up ? "text-gain" : "text-loss"
                    }`}
                  >
                    {price ? fmtPct(changePct) : ""}
                  </td>
                  <td className="px-1 py-1.5">
                    <Sparkline prices={spark} />
                  </td>
                  <td className="pr-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemove(ticker);
                      }}
                      className="text-[#8b949e] opacity-0 transition hover:text-loss group-hover:opacity-100"
                      aria-label={`Remove ${ticker}`}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {error && (
        <div className="px-3 py-1 text-[11px] text-loss">{error}</div>
      )}

      <form
        onSubmit={handleAdd}
        className="flex gap-1 border-t border-terminal-border p-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Add ticker"
          className="min-w-0 flex-1 rounded border border-terminal-border bg-terminal-bg px-2 py-1 font-mono text-sm uppercase outline-none focus:border-accent-blue"
        />
        <button
          type="submit"
          className="rounded bg-accent-blue px-3 py-1 text-sm font-semibold text-black hover:opacity-90"
        >
          Add
        </button>
      </form>
    </div>
  );
}
