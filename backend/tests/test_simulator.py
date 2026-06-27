import math
from unittest.mock import patch

import numpy as np
import pytest

from market.simulator import (
    EVENT_MAX_MAG,
    EVENT_MIN_MAG,
    SEED_PRICES,
    SimulatorMarketData,
)


@pytest.mark.asyncio
async def test_is_ticker_supported_exactly_the_ten_seed_tickers():
    sim = SimulatorMarketData()

    for ticker in SEED_PRICES:
        assert await sim.is_ticker_supported(ticker) is True
        assert await sim.is_ticker_supported(ticker.lower()) is True

    for ticker in ("PYPL", "FAKE", "BTC", ""):
        assert await sim.is_ticker_supported(ticker) is False


def test_gbm_produces_strictly_positive_prices_over_many_ticks():
    sim = SimulatorMarketData()

    for _ in range(10_000):
        sim._advance_prices()

    assert all(price > 0 for price in sim._prices.values())


@pytest.mark.asyncio
async def test_change_pct_matches_price_and_prev_close():
    sim = SimulatorMarketData()
    sim._advance_prices()
    await sim._push_to_cache()

    for ticker, point in sim.get_all_prices().items():
        expected = (point.price - point.prev_close) / point.prev_close * 100
        assert point.change_pct == pytest.approx(expected)
        assert point.change == pytest.approx(point.price - point.prev_close)


@pytest.mark.asyncio
async def test_direction_consistent_with_price_vs_prev_price():
    sim = SimulatorMarketData()

    for _ in range(50):
        sim._advance_prices()
    await sim._push_to_cache()

    for ticker, point in sim.get_all_prices().items():
        if point.price > point.prev_price:
            assert point.direction == "up"
        elif point.price < point.prev_price:
            assert point.direction == "down"
        else:
            assert point.direction == "flat"


def test_event_spike_lands_within_configured_magnitude_range():
    sim = SimulatorMarketData()
    price_before = dict(sim._prices)

    # Force every ticker to take the "event" branch: random.random() always
    # returns 0.0 (< EVENT_PROBABILITY for the trigger check, and the
    # subsequent ">0.5" direction check deterministically picks direction=-1).
    # np.random.standard_normal returns zeros so the GBM diffusion term is
    # negligible, isolating the event's contribution to the price change.
    with patch("market.simulator.random.random", return_value=0.0), \
         patch("market.simulator.random.uniform", return_value=EVENT_MIN_MAG + 0.01), \
         patch("market.simulator.np.random.standard_normal",
               return_value=np.zeros(len(SEED_PRICES))):
        sim._advance_prices()

    for ticker, new_price in sim._prices.items():
        pct_change = (new_price - price_before[ticker]) / price_before[ticker]
        assert -0.04 < pct_change < -0.02  # ~ -(EVENT_MIN_MAG + 0.01) == -0.03


def test_event_magnitude_constants_are_sane():
    assert 0 < EVENT_MIN_MAG < EVENT_MAX_MAG < 1


@pytest.mark.asyncio
async def test_start_seeds_cache_before_tick_loop_runs():
    sim = SimulatorMarketData()
    await sim.start()
    try:
        prices = sim.get_all_prices()
        assert set(prices.keys()) == set(SEED_PRICES.keys())
        for ticker, point in prices.items():
            assert point.price == SEED_PRICES[ticker]
    finally:
        await sim.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task_cleanly():
    sim = SimulatorMarketData()
    await sim.start()
    await sim.stop()

    assert sim._task.cancelled() or sim._task.done()


def test_correlated_tickers_show_expected_correlation_structure():
    sim = SimulatorMarketData()
    returns: dict[str, list[float]] = {t: [] for t in SEED_PRICES}

    # Suppress random events so the Cholesky-correlated GBM signal is not
    # swamped by the much-larger uncorrelated event spikes (~300x variance).
    with patch("market.simulator.random.random", return_value=1.0):
        for _ in range(8_000):
            before = dict(sim._prices)
            sim._advance_prices()
            for ticker in SEED_PRICES:
                returns[ticker].append(math.log(sim._prices[ticker] / before[ticker]))

    aapl_googl_corr = np.corrcoef(returns["AAPL"], returns["GOOGL"])[0, 1]
    jpm_nflx_corr = np.corrcoef(returns["JPM"], returns["NFLX"])[0, 1]

    # AAPL/GOOGL configured at 0.70 correlation; JPM/NFLX at 0.22.
    assert aapl_googl_corr > 0.5
    assert aapl_googl_corr > jpm_nflx_corr
