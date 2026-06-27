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
