"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePortfolio } from "../context/PortfolioContext";
import { fmtMoney } from "../lib/format";

export default function PnLChart() {
  const { history } = usePortfolio();

  const data = useMemo(
    () =>
      history.map((h) => ({
        t: new Date(h.recorded_at).getTime(),
        value: h.total_value,
      })),
    [history]
  );

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-terminal-border px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#8b949e]">
        Portfolio Value
      </div>
      <div className="min-h-0 flex-1 p-2">
        {data.length < 2 ? (
          <div className="flex h-full items-center justify-center text-sm text-[#8b949e]">
            Collecting data…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <defs>
                <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#209dd7" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#209dd7" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                scale="time"
                tick={{ fill: "#8b949e", fontSize: 10 }}
                tickFormatter={(t) =>
                  new Date(t).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                }
                stroke="#30363d"
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fill: "#8b949e", fontSize: 10 }}
                tickFormatter={(v) => `$${Math.round(v).toLocaleString()}`}
                width={60}
                stroke="#30363d"
              />
              <Tooltip
                contentStyle={{
                  background: "#161b22",
                  border: "1px solid #30363d",
                  borderRadius: 6,
                  fontSize: 12,
                }}
                labelStyle={{ color: "#8b949e" }}
                labelFormatter={(t) => new Date(t as number).toLocaleString()}
                formatter={(v) => [fmtMoney(Number(v)), "Value"]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#209dd7"
                strokeWidth={2}
                fill="url(#pnlFill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
