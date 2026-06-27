# Market Data Backend — Design Document

This document is the consolidated design for the FinAlly market data subsystem: the unified `MarketDataSource` interface, the GBM-based simulator, and the Massive (Polygon.io) REST client. It pulls together `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, and `MASSIVE_API.md` into one buildable spec with complete code for `backend/market/`.

---

## 1. Goals

- One environment variable (`MASSIVE_API_KEY`) selects the active data source; all other code is agnostic to which one is running.
- Both implementations expose the identical `MarketDataSource` interface and emit the same `PricePoint` shape.
- Runs in-process as an `asyncio` background task inside FastAPI — no subprocess, no extra container.
- Simulator: realistic-looking GBM price action, correlated across tickers, with occasional event spikes. Fixed universe of 10 tickers.
- Massive: real quotes polled on an interval that respects the free-tier rate limit (5 req/min), any valid US equity symbol supported.
- Failures in the data source (HTTP errors, rate limits) are logged and retried — they never crash the server or stall the SSE stream.

---

## 2. File Layout

```
backend/
└── market/
    ├── __init__.py
    ├── base.py        # PricePoint dataclass, MarketDataSource ABC
    ├── cache.py        # PriceCache (shared in-memory store)
    ├── simulator.py    # SimulatorMarketData (GBM)
    ├── massive.py      # MassiveMarketData (Polygon/Massive REST polling)
    └── factory.py      # create_market_data_source() — the only selection point
```

Dependencies to add to `backend/pyproject.toml`: `numpy` (Cholesky decomposition for correlated returns), `requests` (Massive REST calls; run in a thread executor since it's blocking).

---

## 3. Data Contract — `PricePoint`

Every consumer (SSE stream, portfolio valuation, watchlist) reads this shape and nothing source-specific.

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | `str` | Always uppercase |
| `price` | `float` | Current price |
| `prev_price` | `float` | Price on the previous tick (drives flash direction) |
| `prev_close` | `float` | Previous trading day's close (drives daily % change) |
| `change` | `float` | `price - prev_close` |
| `change_pct` | `float` | `change / prev_close * 100` |
| `timestamp` | `float` | Unix seconds, UTC |
| `direction` | `str` | `"up"`, `"down"`, or `"flat"` vs `prev_price` |

```python
# backend/market/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PricePoint:
    ticker: str
    price: float
    prev_price: float
    prev_close: float
    change: float
    change_pct: float
    timestamp: float
    direction: str  # "up" | "down" | "flat"


class MarketDataSource(ABC):
    """Selected once at startup by create_market_data_source(). Implementations:
    SimulatorMarketData, MassiveMarketData."""

    @abstractmethod
    async def start(self) -> None:
        """Start the background price-update loop (FastAPI lifespan startup)."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background loop cleanly (FastAPI lifespan shutdown)."""

    @abstractmethod
    def get_price(self, ticker: str) -> Optional[PricePoint]:
        """Latest cached price for one ticker, or None if not yet known."""

    @abstractmethod
    def get_prices(self, tickers: list[str]) -> dict[str, PricePoint]:
        """Latest cached prices for the given tickers (missing ones omitted)."""

    @abstractmethod
    def get_all_prices(self) -> dict[str, PricePoint]:
        """Latest cached prices for every known ticker."""

    @abstractmethod
    def is_ticker_supported(self, ticker: str) -> bool:
        """Whether this ticker may be added to the watchlist on this source."""
```

---

## 4. Shared Price Cache

Both implementations write into the same structure; SSE handlers and route handlers read from it. `asyncio.Lock` is sufficient since everything runs on a single event loop — no multiprocessing involved.

```python
# backend/market/cache.py
import asyncio
from typing import Optional

from .base import PricePoint


class PriceCache:
    """In-memory latest-price store. Written by the background market task,
    read by SSE stream handlers and REST routes."""

    def __init__(self) -> None:
        self._data: dict[str, PricePoint] = {}
        self._lock = asyncio.Lock()

    async def update(self, points: list[PricePoint]) -> None:
        async with self._lock:
            for point in points:
                self._data[point.ticker] = point

    async def get(self, ticker: str) -> Optional[PricePoint]:
        async with self._lock:
            return self._data.get(ticker)

    async def get_many(self, tickers: list[str]) -> dict[str, PricePoint]:
        async with self._lock:
            return {t: self._data[t] for t in tickers if t in self._data}

    async def get_all(self) -> dict[str, PricePoint]:
        async with self._lock:
            return dict(self._data)
```

Note: implementations below read `cache._data` directly (synchronously) from their own `get_price`/`get_prices`/`get_all_prices` methods rather than awaiting the lock. This is intentional — those methods are called from sync contexts (e.g. building SSE payloads in a tight loop) and a dict read/snapshot in CPython is already atomic enough for "latest price" reads; only `update()` needs the lock since it's the only writer plus the only place doing multi-key mutation.

---

## 5. Simulator — `SimulatorMarketData`

Geometric Brownian Motion (GBM), correlated across tickers via a Cholesky-factored correlation matrix, with rare random event spikes. Fixed 10-ticker universe; cannot add tickers in simulator mode.

**Formula per tick:** `S(t+dt) = S(t) * exp((μ - σ²/2)·dt + σ·√dt·Z)`, with `dt = 0.5s / (252 days × 6.5h × 3600s) ≈ 8.5e-8` years per 500ms tick.

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
    "AAPL": 190.0, "GOOGL": 175.0, "MSFT": 415.0, "AMZN": 185.0, "TSLA": 175.0,
    "NVDA": 875.0, "META": 490.0, "JPM": 200.0, "V": 275.0, "NFLX": 620.0,
}

# (annual drift, annual volatility) per ticker
TICKER_PARAMS: dict[str, tuple[float, float]] = {
    "AAPL": (0.05, 0.22), "GOOGL": (0.06, 0.24), "MSFT": (0.07, 0.20),
    "AMZN": (0.08, 0.26), "TSLA": (0.10, 0.55), "NVDA": (0.12, 0.50),
    "META": (0.09, 0.30), "JPM": (0.04, 0.18), "V": (0.04, 0.15), "NFLX": (0.07, 0.35),
}

_TICKERS_ORDERED = list(SEED_PRICES.keys())

# Sector-grouped correlation: tech moves together, financials move together
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
_CHOLESKY = np.linalg.cholesky(_CORRELATION_MATRIX)  # computed once at import time

_DT = TICK_INTERVAL / (252 * 6.5 * 3600)  # tick length in trading-years

EVENT_PROBABILITY = 0.001  # per ticker, per tick (~1 spike / 1000 ticks globally)
EVENT_MIN_MAG = 0.02
EVENT_MAX_MAG = 0.05


class SimulatorMarketData(MarketDataSource):
    """GBM price simulator with cross-ticker correlation and event spikes.
    Only the 10 seed tickers are supported."""

    def __init__(self, cache: Optional[PriceCache] = None) -> None:
        self._cache = cache or PriceCache()
        self._prices: dict[str, float] = dict(SEED_PRICES)
        self._prev_prices: dict[str, float] = dict(SEED_PRICES)
        self._prev_closes: dict[str, float] = dict(SEED_PRICES)
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        await self._push_to_cache()  # seed cache before any SSE client connects
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
            except Exception:
                log.exception("Simulator tick error")
            await asyncio.sleep(TICK_INTERVAL)

    def _advance_prices(self) -> None:
        independent_z = np.random.standard_normal(len(_TICKERS_ORDERED))
        correlated_z = _CHOLESKY @ independent_z

        for i, ticker in enumerate(_TICKERS_ORDERED):
            drift, vol = TICKER_PARAMS[ticker]
            z = correlated_z[i]

            log_return = (drift - 0.5 * vol ** 2) * _DT + vol * math.sqrt(_DT) * z
            new_price = self._prices[ticker] * math.exp(log_return)

            if random.random() < EVENT_PROBABILITY:
                magnitude = random.uniform(EVENT_MIN_MAG, EVENT_MAX_MAG)
                direction = 1 if random.random() > 0.5 else -1
                new_price *= (1 + direction * magnitude)
                log.debug("Event spike on %s: %+.2f%%", ticker, direction * magnitude * 100)

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
            direction = "up" if price > prev_price else "down" if price < prev_price else "flat"

            points.append(PricePoint(
                ticker=ticker, price=price, prev_price=prev_price, prev_close=prev_close,
                change=change, change_pct=change_pct, timestamp=now, direction=direction,
            ))

        await self._cache.update(points)
```

**Note on `prev_close`:** the simulator has no real "trading day" boundary. `prev_close` is initialized to the seed price at startup and never reset, so the daily % change shown on a long-running container drifts from "vs. yesterday" toward "vs. container start." That's acceptable for a demo; a future enhancement could snapshot `prev_close` on a wall-clock day rollover.

---

## 6. Massive API — `MassiveMarketData`

Polls `GET /v2/snapshot/locale/us/markets/stocks/tickers` for the union of watched tickers on `PRICE_POLL_INTERVAL_SECONDS` (default 15s, matching the free tier's 5 req/min cap). `requests` is blocking, so calls run via `loop.run_in_executor`. Any valid US equity symbol is supported; validity is checked by hitting the single-ticker snapshot endpoint and checking for a 404 / non-OK status.

```python
# backend/market/massive.py
import asyncio
import logging
import time
from typing import Optional

import requests

from .base import MarketDataSource, PricePoint
from .cache import PriceCache

log = logging.getLogger(__name__)

BASE_URL = "https://api.polygon.io"
SNAPSHOT_URL = f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"


class MassiveMarketData(MarketDataSource):
    """Polls the Massive (Polygon.io) REST snapshot endpoint on an interval.
    Any valid US equity symbol is supported."""

    def __init__(
        self,
        api_key: str,
        poll_interval: float = 15.0,
        cache: Optional[PriceCache] = None,
    ) -> None:
        self._api_key = api_key
        self._poll_interval = poll_interval
        self._cache = cache or PriceCache()
        self._tickers: set[str] = set()
        self._prev_prices: dict[str, float] = {}
        self._task: Optional[asyncio.Task] = None

    def register_ticker(self, ticker: str) -> None:
        """Called when a ticker is added to the watchlist."""
        self._tickers.add(ticker.upper())

    def unregister_ticker(self, ticker: str) -> None:
        """Called when a ticker is removed from the watchlist."""
        self._tickers.discard(ticker.upper())

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())
        log.info("MassiveMarketData started (interval=%.1fs)", self._poll_interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("MassiveMarketData stopped")

    def get_price(self, ticker: str) -> Optional[PricePoint]:
        return self._cache._data.get(ticker.upper())

    def get_prices(self, tickers: list[str]) -> dict[str, PricePoint]:
        return {t.upper(): self._cache._data[t.upper()]
                for t in tickers if t.upper() in self._cache._data}

    def get_all_prices(self) -> dict[str, PricePoint]:
        return dict(self._cache._data)

    def is_ticker_supported(self, ticker: str) -> bool:
        return self._validate_ticker(ticker.upper())

    def _validate_ticker(self, ticker: str) -> bool:
        try:
            resp = requests.get(
                f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
                params={"apiKey": self._api_key},
                timeout=5,
            )
            if resp.status_code == 404:
                return False
            return resp.json().get("status") == "OK"
        except Exception:
            log.warning("Ticker validation failed for %s", ticker, exc_info=True)
            return False

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._fetch_and_update()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Massive poll error")
            await asyncio.sleep(self._poll_interval)

    async def _fetch_and_update(self) -> None:
        if not self._tickers:
            return

        tickers_str = ",".join(sorted(self._tickers))
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._fetch_snapshots, tickers_str)
        if not raw:
            return

        now = time.time()
        points: list[PricePoint] = []

        for snap in raw:
            ticker = snap.get("ticker", "")
            last_trade = snap.get("lastTrade") or {}
            prev_day = snap.get("prevDay") or {}

            price = last_trade.get("p") or snap.get("day", {}).get("c") or 0.0
            prev_close = prev_day.get("c") or price
            prev_price = self._prev_prices.get(ticker, price)

            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0.0
            direction = "up" if price > prev_price else "down" if price < prev_price else "flat"

            self._prev_prices[ticker] = price

            points.append(PricePoint(
                ticker=ticker, price=price, prev_price=prev_price, prev_close=prev_close,
                change=change, change_pct=change_pct, timestamp=now, direction=direction,
            ))

        await self._cache.update(points)
        log.debug("Massive poll: updated %d tickers", len(points))

    def _fetch_snapshots(self, tickers_str: str) -> list[dict]:
        resp = requests.get(
            SNAPSHOT_URL,
            params={"tickers": tickers_str, "apiKey": self._api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            log.warning("Massive API non-OK status: %s", data.get("status"))
            return []
        return data.get("tickers") or []
```

**Rate-limit handling:** the poll loop already serializes calls at `poll_interval` seconds apart, which keeps the free tier (5 req/min → ≥12s between calls) safely under the limit at the default 15s. If a `429` slips through anyway, `resp.raise_for_status()` raises, the exception is logged by `_poll_loop`, and the loop retries on the next scheduled tick — no separate backoff needed since the interval itself is the backoff.

---

## 7. Factory — Single Selection Point

```python
# backend/market/factory.py
import os

from .base import MarketDataSource
from .cache import PriceCache
from .massive import MassiveMarketData
from .simulator import SimulatorMarketData

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def create_market_data_source() -> MarketDataSource:
    """MASSIVE_API_KEY set (non-empty) -> MassiveMarketData; otherwise -> SimulatorMarketData."""
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    poll_interval = float(os.getenv("PRICE_POLL_INTERVAL_SECONDS", "15"))
    cache = PriceCache()

    if api_key:
        source = MassiveMarketData(api_key=api_key, poll_interval=poll_interval, cache=cache)
        for ticker in DEFAULT_TICKERS:
            source.register_ticker(ticker)
        return source

    return SimulatorMarketData(cache=cache)
```

---

## 8. FastAPI Wiring

```python
# backend/main.py
import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sse_starlette.sse import EventSourceResponse

from .market.base import MarketDataSource
from .market.factory import create_market_data_source
from .market.massive import MassiveMarketData

market: MarketDataSource | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global market
    market = create_market_data_source()
    await market.start()
    yield
    await market.stop()


app = FastAPI(lifespan=lifespan)


def get_market() -> MarketDataSource:
    return market


@app.get("/api/stream/prices")
async def stream_prices(mkt: MarketDataSource = Depends(get_market)):
    async def event_generator():
        while True:
            for point in mkt.get_all_prices().values():
                yield {
                    "data": json.dumps({
                        "ticker": point.ticker,
                        "price": point.price,
                        "prev_price": point.prev_price,
                        "change": point.change,
                        "change_pct": point.change_pct,
                        "direction": point.direction,
                        "timestamp": point.timestamp,
                    })
                }
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@app.post("/api/watchlist")
async def add_to_watchlist(body: "AddTickerRequest", mkt: MarketDataSource = Depends(get_market)):
    ticker = body.ticker.upper()
    if not mkt.is_ticker_supported(ticker):
        raise HTTPException(400, f"Ticker {ticker} is not supported by the active data source")

    # db.add_watchlist_entry(ticker)  # persistence layer, see PLAN.md §7

    if isinstance(mkt, MassiveMarketData):
        mkt.register_ticker(ticker)

    return {"ticker": ticker, "status": "added"}


@app.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, mkt: MarketDataSource = Depends(get_market)):
    ticker = ticker.upper()
    # ... reject if an open position exists, then db.remove_watchlist_entry(ticker) ...

    if isinstance(mkt, MassiveMarketData):
        mkt.unregister_ticker(ticker)

    return {"ticker": ticker, "status": "removed"}
```

---

## 9. Testing Targets

**Simulator (`backend/market/simulator.py`):**
- GBM produces strictly positive prices over 10,000 ticks.
- `change_pct == (price - prev_close) / prev_close * 100`.
- `direction` consistent with `price` vs `prev_price`.
- Event spikes land within `[EVENT_MIN_MAG, EVENT_MAX_MAG]`.
- `is_ticker_supported` is `True` for exactly the 10 seed tickers.
- Correlated normals show the expected correlation structure (statistical test, large N — e.g. sample correlation of AAPL/GOOGL returns over many ticks should land near 0.70).

**Massive (`backend/market/massive.py`):**
- Snapshot response parsing maps `lastTrade.p` / `prevDay.c` correctly into `PricePoint` (mock `requests.get`).
- Missing `lastTrade` falls back to `day.c`.
- `is_ticker_supported` returns `False` on a 404 and `True` on `status: "OK"`.
- Poll loop continues (doesn't crash, logs and retries) after a simulated exception or non-200 response.
- `register_ticker`/`unregister_ticker` correctly change which tickers are included in the next poll's `tickers` query param.

**Factory:**
- `MASSIVE_API_KEY` unset/empty → `SimulatorMarketData`.
- `MASSIVE_API_KEY` set → `MassiveMarketData`, pre-registered with the 10 default tickers.

Both implementations can be exercised standalone without FastAPI:

```python
import asyncio
from backend.market.simulator import SimulatorMarketData

async def main():
    sim = SimulatorMarketData()
    await sim.start()
    for _ in range(10):
        await asyncio.sleep(0.5)
        print({t: f"${p.price:.2f} ({p.direction})" for t, p in sim.get_all_prices().items()})
    await sim.stop()

asyncio.run(main())
```

---

## 10. Configuration Summary

| Variable | Default | Effect |
|----------|---------|--------|
| `MASSIVE_API_KEY` | unset | Unset/empty → simulator; set → Massive REST polling |
| `PRICE_POLL_INTERVAL_SECONDS` | `15` | Massive poll cadence only; no effect on simulator or SSE (both fixed at 500ms) |

| Parameter | Value |
|-----------|-------|
| SSE push cadence | 500ms (fixed, both sources) |
| Simulator tick interval | 500ms (fixed) |
| Simulator universe | 10 fixed tickers (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX) |
| Simulator drift / vol range | 4–12% / 15–55% annualized, per ticker |
| Simulator event probability | 0.1% per ticker per tick |
| Simulator event magnitude | 2–5%, random direction |
| Massive free-tier rate limit | 5 req/min → poll interval should stay ≥ 12s |
