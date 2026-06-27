# Market Simulator

This document describes the approach and code structure for the built-in stock price simulator used when `MASSIVE_API_KEY` is not set. It implements the `MarketDataSource` interface defined in `MARKET_INTERFACE.md`.

---

## Goals

- Generate prices that look and feel like real market data — not random noise
- Support correlated moves across related tickers (tech stocks move together)
- Produce occasional dramatic spikes for visual drama
- Run entirely in-process with no external dependencies
- Update the price cache at ~500ms intervals

---

## Algorithm: Geometric Brownian Motion (GBM)

GBM is the standard model for stock price simulation. It produces returns that are log-normally distributed (prices can never go negative, and percentage changes are symmetric in log space — consistent with real market behavior).

**The formula for each tick:**

```
S(t+dt) = S(t) * exp((μ - σ²/2) * dt + σ * √dt * Z)
```

Where:
- `S(t)` — current price
- `μ` — drift (annualized expected return, e.g. 0.05 for 5%/year)
- `σ` — volatility (annualized standard deviation, e.g. 0.25 for 25%/year)
- `dt` — time step in years (0.5s ÷ (252 trading days × 6.5 hours × 3600 seconds) ≈ 8.5e-8)
- `Z` — standard normal random variable

At 500ms intervals with typical volatility (σ = 0.25), the per-tick standard deviation of returns is about **0.016%** — small enough to look realistic tick-by-tick while accumulating meaningful intraday moves.

---

## Seed Prices

Prices start from values that approximate real-world magnitudes. On each fresh start (new Docker volume), these are the initial prices:

```python
SEED_PRICES = {
    "AAPL":  190.0,
    "GOOGL": 175.0,
    "MSFT":  415.0,
    "AMZN":  185.0,
    "TSLA":  175.0,
    "NVDA":  875.0,
    "META":  490.0,
    "JPM":   200.0,
    "V":     275.0,
    "NFLX":  620.0,
}
```

These are the only supported tickers in simulator mode. The simulator does not support adding arbitrary tickers (`is_ticker_supported` returns `False` for any ticker not in this list).

---

## Per-Ticker Parameters

Each ticker has its own drift and volatility. Higher-volatility tickers (TSLA, NVDA) move more per tick.

```python
TICKER_PARAMS = {
    #          drift   volatility
    "AAPL":  (0.05,   0.22),
    "GOOGL": (0.06,   0.24),
    "MSFT":  (0.07,   0.20),
    "AMZN":  (0.08,   0.26),
    "TSLA":  (0.10,   0.55),   # high vol
    "NVDA":  (0.12,   0.50),   # high vol
    "META":  (0.09,   0.30),
    "JPM":   (0.04,   0.18),   # lower vol (financials)
    "V":     (0.04,   0.15),   # lower vol (financials)
    "NFLX":  (0.07,   0.35),
}
```

---

## Correlated Moves

Real stocks do not move independently. Tech stocks tend to move together on macro news. The simulator implements this via a **Cholesky decomposition of a correlation matrix**.

**How it works:**
1. Generate a vector of independent standard normals `Z = [z₁, z₂, ..., z₁₀]`
2. Multiply by the Cholesky factor `L` of the correlation matrix: `Z_corr = L @ Z`
3. Use `Z_corr[i]` as the `Z` term in the GBM formula for ticker `i`

**Correlation structure (approximate):**

```python
# Grouped by sector:
# Tech: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META
# Finance: JPM, V
# Media: NFLX

CORRELATION_MATRIX = [
    # AAPL  GOOGL  MSFT  AMZN  TSLA  NVDA  META  JPM   V    NFLX
    [1.00,  0.70,  0.72, 0.65, 0.45, 0.60, 0.65, 0.35, 0.30, 0.40],  # AAPL
    [0.70,  1.00,  0.68, 0.70, 0.40, 0.58, 0.68, 0.30, 0.28, 0.45],  # GOOGL
    [0.72,  0.68,  1.00, 0.62, 0.42, 0.55, 0.63, 0.38, 0.32, 0.38],  # MSFT
    [0.65,  0.70,  0.62, 1.00, 0.42, 0.55, 0.65, 0.30, 0.25, 0.42],  # AMZN
    [0.45,  0.40,  0.42, 0.42, 1.00, 0.60, 0.45, 0.20, 0.18, 0.38],  # TSLA
    [0.60,  0.58,  0.55, 0.55, 0.60, 1.00, 0.58, 0.25, 0.22, 0.40],  # NVDA
    [0.65,  0.68,  0.63, 0.65, 0.45, 0.58, 1.00, 0.30, 0.28, 0.50],  # META
    [0.35,  0.30,  0.38, 0.30, 0.20, 0.25, 0.30, 1.00, 0.65, 0.22],  # JPM
    [0.30,  0.28,  0.32, 0.25, 0.18, 0.22, 0.28, 0.65, 1.00, 0.20],  # V
    [0.40,  0.45,  0.38, 0.42, 0.38, 0.40, 0.50, 0.22, 0.20, 1.00],  # NFLX
]
```

The Cholesky factor is computed once at startup using `numpy.linalg.cholesky`.

---

## Random Events

Roughly every 20–60 seconds, one ticker is hit with a sudden 2–5% price spike (positive or negative). This simulates earnings surprises, news events, and other market catalysts — adding visual drama and making the heatmap more interesting.

**Event parameters:**
- Probability per tick: `0.001` (roughly one event every ~1000 ticks = 500 seconds)
- Magnitude: uniform random between `2%` and `5%`
- Direction: 50/50 positive or negative
- Duration: single tick (price reverts to GBM path on next tick; no mean reversion needed)

---

## Full Implementation

```python
# backend/market/simulator.py
import asyncio
import logging
import math
import random
import time
from typing import Optional

import numpy as np

from .base import MarketDataSource, PricePoint
from .cache import PriceCache

log = logging.getLogger(__name__)

TICK_INTERVAL = 0.5  # seconds between price updates

SEED_PRICES: dict[str, float] = {
    "AAPL":  190.0,
    "GOOGL": 175.0,
    "MSFT":  415.0,
    "AMZN":  185.0,
    "TSLA":  175.0,
    "NVDA":  875.0,
    "META":  490.0,
    "JPM":   200.0,
    "V":     275.0,
    "NFLX":  620.0,
}

TICKER_PARAMS: dict[str, tuple[float, float]] = {
    "AAPL":  (0.05, 0.22),
    "GOOGL": (0.06, 0.24),
    "MSFT":  (0.07, 0.20),
    "AMZN":  (0.08, 0.26),
    "TSLA":  (0.10, 0.55),
    "NVDA":  (0.12, 0.50),
    "META":  (0.09, 0.30),
    "JPM":   (0.04, 0.18),
    "V":     (0.04, 0.15),
    "NFLX":  (0.07, 0.35),
}

_TICKERS_ORDERED = list(SEED_PRICES.keys())

_CORRELATION_MATRIX = np.array([
    [1.00, 0.70, 0.72, 0.65, 0.45, 0.60, 0.65, 0.35, 0.30, 0.40],
    [0.70, 1.00, 0.68, 0.70, 0.40, 0.58, 0.68, 0.30, 0.28, 0.45],
    [0.72, 0.68, 1.00, 0.62, 0.42, 0.55, 0.63, 0.38, 0.32, 0.38],
    [0.65, 0.70, 0.62, 1.00, 0.42, 0.55, 0.65, 0.30, 0.25, 0.42],
    [0.45, 0.40, 0.42, 0.42, 1.00, 0.60, 0.45, 0.20, 0.18, 0.38],
    [0.60, 0.58, 0.55, 0.55, 0.60, 1.00, 0.58, 0.25, 0.22, 0.40],
    [0.65, 0.68, 0.63, 0.65, 0.45, 0.58, 1.00, 0.30, 0.28, 0.50],
    [0.35, 0.30, 0.38, 0.30, 0.20, 0.25, 0.30, 1.00, 0.65, 0.22],
    [0.30, 0.28, 0.32, 0.25, 0.18, 0.22, 0.28, 0.65, 1.00, 0.20],
    [0.40, 0.45, 0.38, 0.42, 0.38, 0.40, 0.50, 0.22, 0.20, 1.00],
])

# Pre-compute Cholesky factor once at module load
_CHOLESKY = np.linalg.cholesky(_CORRELATION_MATRIX)

# Time step in years: 0.5s / (252 trading days * 6.5 hours * 3600 s/hr)
_DT = TICK_INTERVAL / (252 * 6.5 * 3600)

EVENT_PROBABILITY = 0.001    # per tick, per-ticker; ~1 event per 1000 ticks globally
EVENT_MIN_MAG = 0.02         # 2% minimum spike
EVENT_MAX_MAG = 0.05         # 5% maximum spike


class SimulatorMarketData(MarketDataSource):
    """
    Generates synthetic stock prices using Geometric Brownian Motion with
    correlated moves across tickers and occasional random event spikes.
    Only the 10 default seed tickers are supported.
    """

    def __init__(self, cache: Optional[PriceCache] = None) -> None:
        self._cache = cache or PriceCache()
        self._prices: dict[str, float] = dict(SEED_PRICES)
        self._prev_prices: dict[str, float] = dict(SEED_PRICES)
        # Use first price as prev_close since we have no real market history
        self._prev_closes: dict[str, float] = dict(SEED_PRICES)
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        # Seed the cache with initial prices before any SSE client connects
        await self._push_to_cache()
        self._task = asyncio.create_task(self._tick_loop())
        log.info("SimulatorMarketData started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("SimulatorMarketData stopped")

    def get_price(self, ticker: str) -> Optional[PricePoint]:
        return self._cache._data.get(ticker.upper())

    def get_prices(self, tickers: list[str]) -> dict[str, PricePoint]:
        return {t.upper(): self._cache._data[t.upper()]
                for t in tickers if t.upper() in self._cache._data}

    def get_all_prices(self) -> dict[str, PricePoint]:
        return dict(self._cache._data)

    def is_ticker_supported(self, ticker: str) -> bool:
        return ticker.upper() in SEED_PRICES

    async def _tick_loop(self) -> None:
        while True:
            try:
                self._advance_prices()
                await self._push_to_cache()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Simulator tick error: %s", exc)
            await asyncio.sleep(TICK_INTERVAL)

    def _advance_prices(self) -> None:
        # Generate correlated standard normals using Cholesky decomposition
        independent_z = np.random.standard_normal(len(_TICKERS_ORDERED))
        correlated_z = _CHOLESKY @ independent_z

        for i, ticker in enumerate(_TICKERS_ORDERED):
            drift, vol = TICKER_PARAMS[ticker]
            z = correlated_z[i]

            # GBM step
            log_return = (drift - 0.5 * vol ** 2) * _DT + vol * math.sqrt(_DT) * z
            new_price = self._prices[ticker] * math.exp(log_return)

            # Random event spike
            if random.random() < EVENT_PROBABILITY:
                magnitude = random.uniform(EVENT_MIN_MAG, EVENT_MAX_MAG)
                direction = 1 if random.random() > 0.5 else -1
                new_price *= (1 + direction * magnitude)
                log.debug("Event spike on %s: %.2f%%", ticker, direction * magnitude * 100)

            self._prev_prices[ticker] = self._prices[ticker]
            self._prices[ticker] = round(new_price, 4)

    async def _push_to_cache(self) -> None:
        now = time.time()
        points: list[PricePoint] = []

        for ticker in _TICKERS_ORDERED:
            price = self._prices[ticker]
            prev_price = self._prev_prices[ticker]
            prev_close = self._prev_closes[ticker]

            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0.0

            if price > prev_price:
                direction = "up"
            elif price < prev_price:
                direction = "down"
            else:
                direction = "flat"

            points.append(PricePoint(
                ticker=ticker,
                price=price,
                prev_price=prev_price,
                prev_close=prev_close,
                change=change,
                change_pct=change_pct,
                timestamp=now,
                direction=direction,
            ))

        await self._cache.update(points)
```

---

## Prev Close Handling

The simulator has no concept of a "previous trading day" since it runs continuously. On each fresh start:

- `prev_close` is initialized to the seed price for each ticker
- As the simulator runs through a simulated "day" (arbitrary duration), `prev_close` could be reset at midnight to the last recorded price — but for simplicity, it is set to the seed price at startup
- The frontend's daily % change display will show change from the seed price, which is sufficient for the demo

A future enhancement could snapshot the "end of day" price at midnight and use it as `prev_close` for the next simulated session.

---

## Testing the Simulator

The simulator can be tested in isolation without running the full FastAPI server:

```python
import asyncio
from backend.market.simulator import SimulatorMarketData

async def main():
    sim = SimulatorMarketData()
    await sim.start()
    for _ in range(10):
        await asyncio.sleep(0.5)
        prices = sim.get_all_prices()
        print({t: f"${p.price:.2f} ({p.direction})" for t, p in prices.items()})
    await sim.stop()

asyncio.run(main())
```

**Unit test targets:**
- GBM produces only positive prices over 10,000 ticks
- `change_pct` matches `(price - prev_close) / prev_close * 100`
- `direction` is consistent with `price` vs `prev_price`
- Event spikes produce moves within `[EVENT_MIN_MAG, EVENT_MAX_MAG]` range
- `is_ticker_supported` returns `True` for all 10 seed tickers and `False` for others
- Correlated normals have approximately the right correlation structure (statistical test with large N)

---

## Configuration Summary

| Parameter | Value | Notes |
|-----------|-------|-------|
| Tick interval | 500ms | Fixed; not configurable |
| Supported tickers | 10 (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX) | Fixed in simulator mode |
| Drift range | 4%–12%/year | Per-ticker; see `TICKER_PARAMS` |
| Volatility range | 15%–55%/year | Per-ticker; higher = more dramatic moves |
| Event probability | 0.1%/tick | ~1 event per ~1000 ticks across all tickers |
| Event magnitude | 2%–5% | Single-tick spike, random direction |
| Correlation model | Cholesky decomposition of 10×10 matrix | Sector-based grouping |
