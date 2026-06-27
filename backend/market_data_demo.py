#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "numpy>=1.26",
#   "requests>=2.31",
# ]
# ///
"""
market_data_demo.py — live demonstration of the FinAlly market data backend.

Runs the GBM simulator for 10 seconds and prints a refreshing price table
to the terminal showing prices, tick direction, and daily % change.

Usage (recommended — uv installs numpy automatically):
    uv run backend/market_data_demo.py

Or with numpy already installed:
    python3 backend/market_data_demo.py
"""

import asyncio
import os
import sys
import time

# Make the market package importable (it lives alongside this script in backend/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from market.simulator import SEED_PRICES, SimulatorMarketData  # noqa: E402

DEMO_DURATION = 10   # seconds to run
REFRESH_RATE  = 0.5  # seconds between screen refreshes

# ANSI colour helpers
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
CLEAR  = "\033[2J\033[H"   # clear screen + move cursor to top


def arrow(direction: str) -> str:
    return {"up": f"{GREEN}▲{RESET}", "down": f"{RED}▼{RESET}", "flat": " "}[direction]


def colour_pct(pct: float) -> str:
    s = f"{pct:+.2f}%"
    return (GREEN if pct > 0 else RED if pct < 0 else "") + s + RESET


def mini_sparkline(history: list[float], width: int = 8) -> str:
    """Return an 8-character ASCII sparkline from the last `width` prices."""
    bars = " ▁▂▃▄▅▆▇█"
    segment = history[-width:] if len(history) >= width else history
    if len(segment) < 2:
        return "." * width
    lo, hi = min(segment), max(segment)
    span = hi - lo or 1
    return "".join(bars[round((p - lo) / span * (len(bars) - 1))] for p in segment)


async def main() -> None:
    sim = SimulatorMarketData()
    await sim.start()

    # Per-ticker price history for sparklines
    history: dict[str, list[float]] = {t: [SEED_PRICES[t]] for t in SEED_PRICES}

    start = time.monotonic()
    ticks = 0

    try:
        while time.monotonic() - start < DEMO_DURATION:
            await asyncio.sleep(REFRESH_RATE)
            prices = sim.get_all_prices()
            ticks += 1

            for ticker, point in prices.items():
                history[ticker].append(point.price)

            elapsed = time.monotonic() - start
            remaining = max(0, DEMO_DURATION - elapsed)

            # Build display
            lines = [
                CLEAR,
                f"{BOLD}FinAlly Market Data Demo{RESET}  "
                f"({elapsed:.1f}s elapsed, {remaining:.0f}s remaining, "
                f"tick #{ticks})",
                "",
                f"  {'TICKER':<6}  {'PRICE':>9}  {'DIR'}  {'CHG %':>8}  {'SPARKLINE (500ms ticks)'}",
                f"  {'-'*6}  {'-'*9}  {'-'*3}  {'-'*8}  {'-'*24}",
            ]

            for ticker in SEED_PRICES:           # stable ordering
                point = prices.get(ticker)
                if not point:
                    continue
                spark = mini_sparkline(history[ticker])
                lines.append(
                    f"  {BOLD}{ticker:<6}{RESET}  "
                    f"${point.price:>8.2f}  "
                    f"{arrow(point.direction)}    "
                    f"{colour_pct(point.change_pct):>8}  "
                    f"{spark}"
                )

            lines += [
                "",
                f"  {YELLOW}Simulator mode — GBM with correlated tickers & event spikes{RESET}",
                f"  Source: backend/market/simulator.py",
            ]

            print("\n".join(lines), end="", flush=True)

    finally:
        await sim.stop()

    # Final summary
    prices = sim.get_all_prices()
    print(f"\n\n{BOLD}Final prices after {ticks} ticks ({DEMO_DURATION}s):{RESET}\n")
    for ticker in SEED_PRICES:
        point = prices.get(ticker)
        if not point:
            continue
        seed = SEED_PRICES[ticker]
        total_change = (point.price - seed) / seed * 100
        print(
            f"  {BOLD}{ticker:<6}{RESET}  "
            f"${point.price:>8.2f}  "
            f"(started ${seed:.2f}, total {colour_pct(total_change)})"
        )
    print()


if __name__ == "__main__":
    asyncio.run(main())
