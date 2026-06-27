"use client";

interface SparklineProps {
  prices: number[];
  width?: number;
  height?: number;
}

export default function Sparkline({
  prices,
  width = 80,
  height = 24,
}: SparklineProps) {
  if (prices.length < 2) {
    return <svg width={width} height={height} aria-hidden />;
  }

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const stepX = width / (prices.length - 1);

  const points = prices
    .map((p, i) => {
      const x = i * stepX;
      const y = height - ((p - min) / span) * (height - 2) - 1;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const rising = prices[prices.length - 1] >= prices[0];
  const color = rising ? "#3fb950" : "#f85149";

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
