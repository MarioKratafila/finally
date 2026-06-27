import pytest

from market.factory import DEFAULT_TICKERS, create_market_data_source
from market.massive import MassiveMarketData
from market.simulator import SimulatorMarketData


def test_factory_returns_simulator_when_api_key_unset(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    source = create_market_data_source()

    assert isinstance(source, SimulatorMarketData)


def test_factory_returns_simulator_when_api_key_empty(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "   ")

    source = create_market_data_source()

    assert isinstance(source, SimulatorMarketData)


def test_factory_returns_massive_when_api_key_set(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key-123")

    source = create_market_data_source()

    assert isinstance(source, MassiveMarketData)
    assert source._api_key == "test-key-123"
    assert source._tickers == set(DEFAULT_TICKERS)


def test_factory_respects_custom_poll_interval(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key-123")
    monkeypatch.setenv("PRICE_POLL_INTERVAL_SECONDS", "2")

    source = create_market_data_source()

    assert source._poll_interval == pytest.approx(2.0)


def test_factory_default_poll_interval_is_fifteen_seconds(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key-123")
    monkeypatch.delenv("PRICE_POLL_INTERVAL_SECONDS", raising=False)

    source = create_market_data_source()

    assert source._poll_interval == pytest.approx(15.0)
