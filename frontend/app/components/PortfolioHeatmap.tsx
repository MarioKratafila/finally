"use client";

import { useMemo } from "react";
import { usePortfolio } from "../context/PortfolioContext";
import { fmtPct } from "../lib/format";
import type { Position } from "../lib/types";

interface Rect {
  ticker: string;
  pnlPct: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Tile {
  ticker: string;
  value: number;
  pnlPct: number;
}

// Squarified-ish treemap via recursive split on the longer axis.
function layout(
  tiles: Tile[],
  x: number,
  y: number,
  w: number,
  h: number,
  out: Rect[]
) {
  if (tiles.length === 0) return;
  if (tiles.length === 1) {
    const t = tiles[0];
    out.push({ ticker: t.ticker, pnlPct: t.pnlPct, x, y, w, h });
    return;
  }
  const total = tiles.reduce((s, t) => s + t.value, 0);
  let acc = 0;
  let split = 1;
  for (let i = 0; i < tiles.length; i++) {
    acc += tiles[i].value;
    if (acc >= total / 2) {
      split = i + 1;
      break;
    }
  }
  const first = tiles.slice(0, split);
  const rest = tiles.slice(split);
  const firstSum = first.reduce((s, t) => s + t.value, 0);
  const frac = firstSum / total;

  if (w >= h) {
    const fw = w * frac;
    layout(first, x, y, fw, h, out);
    layout(rest, x + fw, y, w - fw, h, out);
  } else {
    const fh = h * frac;
    layout(first, x, y, w, fh, out);
    layout(rest, x, y + fh, w, h - fh, out);
  }
}

function colorFor(pnlPct: number): string {
  const capped = Math.max(-10, Math.min(10, pnlPct));
  const intensity = Math.abs(capped) / 10; // 0..1
  const alpha = 0.25 + intensity * 0.6;
  return pnlPct >= 0
    ? `rgba(63, 185, 80, ${alpha.toFixed(2)})`
    : `rgba(248, 81, 73, ${alpha.toFixed(2)})`;
}

const WIDTH = 1000;
const HEIGHT = 1000;

export default function PortfolioHeatmap() {
  const { portfolio } = usePortfolio();
  const positions: Position[] = portfolio?.positions ?? [];

  const rects = useMemo(() => {
    const tiles: Tile[] = positions
      .map((p) => ({
        ticker: p.ticker,
        value: Math.abs(p.quantity * p.current_price),
        pnlPct: p.pnl_pct,
      }))
      .filter((t) => t.value > 0)
      .sort((a, b) => b.value - a.value);

    const out: Rect[] = [];
    layout(tiles, 0, 0, WIDTH, HEIGHT, out);
    return out;
  }, [positions]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-terminal-border px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#8b949e]">
        Portfolio Heatmap
      </div>
      <div className="flex-1 p-2">
        {rects.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-[#8b949e]">
            No positions yet
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            preserveAspectRatio="none"
            className="h-full w-full"
          >
            {rects.map((r) => (
              <g key={r.ticker}>
                <rect
                  x={r.x}
                  y={r.y}
                  width={r.w}
                  height={r.h}
                  fill={colorFor(r.pnlPct)}
                  stroke="#0d1117"
                  strokeWidth={4}
                />
                <text
                  x={r.x + r.w / 2}
                  y={r.y + r.h / 2 - 8}
                  textAnchor="middle"
                  fill="#e6edf3"
                  fontSize={Math.max(14, Math.min(r.w, r.h) * 0.18)}
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  {r.ticker}
                </text>
                <text
                  x={r.x + r.w / 2}
                  y={r.y + r.h / 2 + 16}
                  textAnchor="middle"
                  fill="#e6edf3"
                  fontSize={Math.max(11, Math.min(r.w, r.h) * 0.13)}
                  fontFamily="monospace"
                >
                  {fmtPct(r.pnlPct)}
                </text>
              </g>
            ))}
          </svg>
        )}
      </div>
    </div>
  );
}
