# Market Data Interface

This document defines the unified Python interface for market data in FinAlly. All downstream code — SSE streaming, price cache, portfolio calculations — works against this interface and is agnostic to whether prices come from the Massive API or the built-in simulator.

---

## Design Goals

- **Single selection point**: one environment variable (`MASSIVE_API_KEY`) determines which implementation is active
- **Identical contract**: both implementations expose the same methods and return the same data shapes
- **In-process operation**: no subprocess, no network proxy — the selected implementation runs as a background task inside FastAPI
- **Graceful degradation**: if the Massive API is unavailable, the system does not crash; it logs and continues

---

## Abstract Base Class

```python
# backend/market/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PricePoint:
    ticker: str
    price: float
    prev_price: float        # previous price before this tick (for flash direction)
    prev_close: float        # previous trading day's close (for daily % change)
    change: float            # price - prev_close
    change_pct: float        # (price - prev_close) / prev_close * 100
    timestamp: float         # Unix seconds (UTC)
    direction: str           # "up", "down", or "flat"


class MarketDataSource(ABC):
    """
    Abstract interface for a market data provider.

    Implementations: MassiveMarketData, SimulatorMarketData.
    Selected at startup by create_market_data_source().
    """

    @abstractmethod
    async def start(self) -> None:
        """
        Start the background price update loop.
        Called once at application startup (FastAPI lifespan).
        """

    @abstractmethod
    async def stop(self) -> None:
        """
        Gracefully stop the background price update loop.
        Called at application shutdown.
        """

    @abstractmethod
    def get_price(self, ticker: str) -> Optional[PricePoint]:
        """
        Return the latest cached price for a single ticker.
        Returns None if the ticker has no data yet.
        """

    @abstractmethod
    def get_prices(self, tickers: list[str]) -> dict[str, PricePoint]:
        """
        Return the latest cached prices for a list of tickers.
        Only tickers with cached data are included in the result.
        """

    @abstractmethod
    def get_all_prices(self) -> dict[str, PricePoint]:
        """
        Return the latest cached prices for all known tickers.
        """

    @abstractmethod
    def is_ticker_supported(self, ticker: str) -> bool:
        """
        Return True if the given ticker can be added to the watchlist.
        Simulator: only the 10 default seed tickers are supported.
        Massive: any valid US equity symbol is supported.
        """
```

---

## Shared Price Cache

Both implementations write into the same in-memory cache. The cache is a plain dict, lock-protected for thread safety between the background update task and the SSE stream readers.

```python
# backend/market/cache.py
import asyncio
from typing import Optional
from .base import PricePoint


class PriceCache:
    """
    Thread-safe in-memory cache for the latest price of each ticker.
    Written by the background market data task; read by SSE stream handlers.
    """

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

---

## Massive API Implementation

Polls the Massive snapshot endpoint at the interval configured by `PRICE_POLL_INTERVAL_SECONDS` (default 15s, matching the free tier's 5 req/min limit). Between polls the cache is not updated — the SSE stream re-sends the same prices until the next poll.

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
    """
    Fetches live stock prices from the Massive (Polygon.io) REST API.
    Polls on a configurable interval; any ticker symbol is supported.
    """

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
        self._prev_closes: dict[str, float] = {}
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
        # Synchronous read from the shared cache dict (safe for SSE handlers)
        return self._cache._data.get(ticker.upper())

    def get_prices(self, tickers: list[str]) -> dict[str, PricePoint]:
        return {t.upper(): self._cache._data[t.upper()]
                for t in tickers if t.upper() in self._cache._data}

    def get_all_prices(self) -> dict[str, PricePoint]:
        return dict(self._cache._data)

    def is_ticker_supported(self, ticker: str) -> bool:
        # Massive supports all valid US equity symbols; validate by querying the API
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
            data = resp.json()
            return data.get("status") == "OK"
        except Exception as exc:
            log.warning("Ticker validation failed for %s: %s", ticker, exc)
            return False

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._fetch_and_update()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Massive poll error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _fetch_and_update(self) -> None:
        if not self._tickers:
            return

        tickers_str = ",".join(sorted(self._tickers))
        loop = asyncio.get_running_loop()

        # Run the blocking HTTP call in a thread pool
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

            if price > prev_price:
                direction = "up"
            elif price < prev_price:
                direction = "down"
            else:
                direction = "flat"

            self._prev_prices[ticker] = price

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

---

## Simulator Implementation

See `MARKET_SIMULATOR.md` for the full simulator design. The simulator implements the same `MarketDataSource` interface:

```python
# backend/market/simulator.py
from .base import MarketDataSource, PricePoint
from .cache import PriceCache

class SimulatorMarketData(MarketDataSource):
    """
    Generates synthetic stock prices using Geometric Brownian Motion.
    See MARKET_SIMULATOR.md for algorithm and configuration details.
    """
    # ... full implementation in simulator.py
```

---

## Factory Function

The single entry point for the rest of the application. Called once at startup, returns the appropriate implementation.

```python
# backend/market/factory.py
import os
from .base import MarketDataSource
from .cache import PriceCache
from .massive import MassiveMarketData
from .simulator import SimulatorMarketData

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def create_market_data_source() -> MarketDataSource:
    """
    Return the active market data implementation based on environment variables.

    MASSIVE_API_KEY set   → MassiveMarketData (real prices from Massive REST API)
    MASSIVE_API_KEY unset → SimulatorMarketData (GBM-based price simulation)
    """
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    poll_interval = float(os.getenv("PRICE_POLL_INTERVAL_SECONDS", "15"))
    cache = PriceCache()

    if api_key:
        source = MassiveMarketData(
            api_key=api_key,
            poll_interval=poll_interval,
            cache=cache,
        )
        # Pre-register default tickers
        for ticker in DEFAULT_TICKERS:
            source.register_ticker(ticker)
        return source
    else:
        return SimulatorMarketData(cache=cache)
```

---

## FastAPI Integration

Wire the market data source into FastAPI's lifespan context so it starts and stops cleanly with the server.

```python
# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .market.factory import create_market_data_source

market: MarketDataSource | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global market
    market = create_market_data_source()
    await market.start()
    yield
    await market.stop()


app = FastAPI(lifespan=lifespan)
```

**Dependency injection for route handlers:**

```python
from fastapi import Depends
from .market.base import MarketDataSource

def get_market() -> MarketDataSource:
    return market  # module-level singleton set during lifespan


@app.get("/api/stream/prices")
async def stream_prices(mkt: MarketDataSource = Depends(get_market)):
    async def event_generator():
        while True:
            prices = mkt.get_all_prices()
            for ticker, point in prices.items():
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
```

---

## Watchlist Integration

When a ticker is added to the watchlist, notify the active market data source:

```python
@app.post("/api/watchlist")
async def add_to_watchlist(body: AddTickerRequest, mkt: MarketDataSource = Depends(get_market)):
    ticker = body.ticker.upper()

    if not mkt.is_ticker_supported(ticker):
        raise HTTPException(400, f"Ticker {ticker} is not supported by the active data source")

    # Save to DB ...
    db.add_watchlist_entry(ticker)

    # Notify the market data source so it starts tracking prices
    if isinstance(mkt, MassiveMarketData):
        mkt.register_ticker(ticker)

    return {"ticker": ticker, "status": "added"}


@app.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, mkt: MarketDataSource = Depends(get_market)):
    ticker = ticker.upper()
    # ... position check, DB removal ...
    if isinstance(mkt, MassiveMarketData):
        mkt.unregister_ticker(ticker)
    return {"ticker": ticker, "status": "removed"}
```

---

## PricePoint Contract (Summary)

All consumers receive `PricePoint` objects. No consumer should depend on Massive-specific or simulator-specific fields.

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | `str` | Ticker symbol, always uppercase |
| `price` | `float` | Current price |
| `prev_price` | `float` | Price from the previous tick (for flash direction) |
| `prev_close` | `float` | Previous day's close (for daily % change display) |
| `change` | `float` | `price - prev_close` |
| `change_pct` | `float` | `(price - prev_close) / prev_close * 100` |
| `timestamp` | `float` | Unix seconds (UTC) when this price was recorded |
| `direction` | `str` | `"up"`, `"down"`, or `"flat"` vs previous tick |

---

## File Layout

```
backend/
└── market/
    ├── __init__.py
    ├── base.py        # PricePoint dataclass, MarketDataSource ABC
    ├── cache.py       # PriceCache (shared in-memory dict)
    ├── factory.py     # create_market_data_source() factory
    ├── massive.py     # MassiveMarketData implementation
    └── simulator.py   # SimulatorMarketData implementation
```
