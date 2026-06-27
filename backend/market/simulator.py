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

    async def is_ticker_supported(self, ticker: str) -> bool:
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
