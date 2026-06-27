import asyncio
from typing import Optional

from .base import PricePoint


class PriceCache:
    """In-memory latest-price store. Written by the background market task,
    read by SSE stream handlers and REST routes.

    `update()` takes the lock since it's the only writer and the only place
    doing multi-key mutation. The synchronous `_data` dict is read directly
    (without the lock) by implementations' get_price/get_prices/get_all_prices
    methods, since those are called from sync contexts and a dict read is
    already atomic enough for "latest price" reads.
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
