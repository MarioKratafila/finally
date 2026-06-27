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
    async def is_ticker_supported(self, ticker: str) -> bool:
        """Whether this ticker may be added to the watchlist on this source."""
