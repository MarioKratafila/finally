import pytest

from market.base import PricePoint
from market.cache import PriceCache


def make_point(ticker: str, price: float = 100.0) -> PricePoint:
    return PricePoint(
        ticker=ticker,
        price=price,
        prev_price=price,
        prev_close=price,
        change=0.0,
        change_pct=0.0,
        timestamp=1.0,
        direction="flat",
    )


@pytest.mark.asyncio
async def test_update_and_get():
    cache = PriceCache()
    await cache.update([make_point("AAPL", 190.0)])

    point = await cache.get("AAPL")
    assert point is not None
    assert point.ticker == "AAPL"
    assert point.price == 190.0


@pytest.mark.asyncio
async def test_get_missing_ticker_returns_none():
    cache = PriceCache()
    assert await cache.get("NOPE") is None


@pytest.mark.asyncio
async def test_get_many_omits_missing_tickers():
    cache = PriceCache()
    await cache.update([make_point("AAPL"), make_point("GOOGL")])

    result = await cache.get_many(["AAPL", "GOOGL", "MISSING"])

    assert set(result.keys()) == {"AAPL", "GOOGL"}


@pytest.mark.asyncio
async def test_get_all_returns_snapshot_copy():
    cache = PriceCache()
    await cache.update([make_point("AAPL")])

    snapshot = await cache.get_all()
    snapshot["AAPL"] = make_point("AAPL", price=999.0)

    # mutating the returned dict must not affect the cache's internal state
    fresh = await cache.get_all()
    assert fresh["AAPL"].price == 100.0


@pytest.mark.asyncio
async def test_update_overwrites_existing_ticker():
    cache = PriceCache()
    await cache.update([make_point("AAPL", price=100.0)])
    await cache.update([make_point("AAPL", price=105.0)])

    point = await cache.get("AAPL")
    assert point.price == 105.0
