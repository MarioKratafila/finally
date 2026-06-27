"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useMarket } from "../context/MarketContext";
import { fmtPct } from "../lib/format";

export default function MainChart({ ticker }: { ticker: string | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const lastTsRef = useRef<number>(0);
  const tickerRef = useRef<string | null>(ticker);

  const { prices } = useMarket();
  const price = ticker ? prices.get(ticker) : undefined;

  // Create chart once.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0d1117" },
        textColor: "#8b949e",
        fontFamily: "monospace",
      },
      grid: {
        vertLines: { color: "#21262d", style: LineStyle.Dotted },
        horzLines: { color: "#21262d", style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: { borderColor: "#30363d", timeVisible: true, secondsVisible: true },
      autoSize: true,
    });
    const series = chart.addAreaSeries({
      lineColor: "#209dd7",
      topColor: "rgba(32, 157, 215, 0.4)",
      bottomColor: "rgba(32, 157, 215, 0.0)",
      lineWidth: 2,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Reset data when ticker changes.
  useEffect(() => {
    tickerRef.current = ticker;
    lastTsRef.current = 0;
    seriesRef.current?.setData([]);
  }, [ticker]);

  // Append ticks.
  useEffect(() => {
    if (!price || !seriesRef.current) return;
    if (tickerRef.current !== price.ticker) return;
    const ts = Math.floor(price.timestamp) as UTCTimestamp;
    if (ts <= lastTsRef.current) return; // lightweight-charts requires increasing time
    lastTsRef.current = ts;
    seriesRef.current.update({ time: ts, value: price.price });
  }, [price]);

  const up = (price?.change_pct ?? 0) >= 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-baseline gap-3 border-b border-terminal-border px-3 py-2">
        {ticker ? (
          <>
            <span className="font-mono text-lg font-bold text-accent-yellow">
              {ticker}
            </span>
            <span className="font-mono text-lg tabular-nums">
              {price ? price.price.toFixed(2) : "—"}
            </span>
            <span
              className={`font-mono text-sm tabular-nums ${
                up ? "text-gain" : "text-loss"
              }`}
            >
              {price ? fmtPct(price.change_pct) : ""}
            </span>
          </>
        ) : (
          <span className="text-sm text-[#8b949e]">
            Select a ticker to view its chart
          </span>
        )}
      </div>
      <div ref={containerRef} className="min-h-0 flex-1" />
    </div>
  );
}
