"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { usePortfolio } from "../context/PortfolioContext";
import { sendChatMessage } from "../lib/api";
import type { ChatResponse, TradeRequest, WatchlistChange } from "../lib/types";

interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  trades?: TradeRequest[];
  watchlist?: WatchlistChange[];
  failed?: ChatResponse["failed_trades"];
}

function Chip({ text, tone }: { text: string; tone: "ok" | "warn" }) {
  const cls =
    tone === "ok"
      ? "border-gain/50 text-gain"
      : "border-loss/50 text-loss";
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[10px] ${cls}`}
    >
      {text}
    </span>
  );
}

export default function ChatPanel({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { refresh } = usePortfolio();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, loading]);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const message = input.trim();
    if (!message || loading) return;
    setTurns((t) => [...t, { role: "user", content: message }]);
    setInput("");
    setLoading(true);
    try {
      const res = await sendChatMessage(message);
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: res.message,
          trades: res.executed_trades ?? res.trades,
          watchlist: res.watchlist_changes,
          failed: res.failed_trades,
        },
      ]);
      await refresh();
    } catch (err) {
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content:
            err instanceof Error
              ? `Error: ${err.message}`
              : "Something went wrong.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  if (collapsed) {
    return (
      <button
        onClick={onToggle}
        className="flex h-full w-10 flex-col items-center justify-center border-l border-terminal-border bg-terminal-panel text-[#8b949e] hover:text-accent-yellow"
        aria-label="Open AI chat"
      >
        <span className="rotate-90 whitespace-nowrap text-xs uppercase tracking-widest">
          AI Chat
        </span>
      </button>
    );
  }

  return (
    <div className="flex h-full w-full flex-col border-l border-terminal-border bg-terminal-panel">
      <div className="flex items-center justify-between border-b border-terminal-border px-3 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-accent-yellow">
          FinAlly Assistant
        </span>
        <button
          onClick={onToggle}
          className="text-[#8b949e] hover:text-accent-yellow"
          aria-label="Collapse chat"
        >
          ›
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-3">
        {turns.length === 0 && (
          <p className="text-xs text-[#8b949e]">
            Ask me about your portfolio, request analysis, or tell me to execute
            trades and manage your watchlist.
          </p>
        )}
        {turns.map((turn, i) => (
          <div
            key={i}
            className={`flex ${
              turn.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                turn.role === "user"
                  ? "bg-accent-blue/20 text-[#e6edf3]"
                  : "bg-terminal-bg text-[#e6edf3]"
              }`}
            >
              <p className="whitespace-pre-wrap">{turn.content}</p>
              {(turn.trades?.length ||
                turn.watchlist?.length ||
                turn.failed?.length) && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {turn.trades?.map((t, j) => (
                    <Chip
                      key={`t${j}`}
                      tone="ok"
                      text={`${t.side.toUpperCase()} ${t.quantity} ${t.ticker}`}
                    />
                  ))}
                  {turn.watchlist?.map((w, j) => (
                    <Chip
                      key={`w${j}`}
                      tone="ok"
                      text={`${w.action.toUpperCase()} ${w.ticker}`}
                    />
                  ))}
                  {turn.failed?.map((f, j) => (
                    <Chip
                      key={`f${j}`}
                      tone="warn"
                      text={`FAIL ${f.side.toUpperCase()} ${f.ticker}`}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="flex gap-1 rounded-lg bg-terminal-bg px-3 py-3">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[#8b949e]" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[#8b949e]" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[#8b949e]" />
            </div>
          </div>
        )}
      </div>

      <form onSubmit={send} className="flex gap-1 border-t border-terminal-border p-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message FinAlly..."
          className="min-w-0 flex-1 rounded border border-terminal-border bg-terminal-bg px-2 py-1.5 text-sm outline-none focus:border-accent-blue"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-accent-purple px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
