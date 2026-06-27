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
