import pytest

from market.base import MarketDataSource, PricePoint
from market.massive import MassiveMarketData
from market.simulator import SimulatorMarketData


def test_price_point_holds_all_contract_fields():
    point = PricePoint(
        ticker="AAPL",
        price=190.5,
        prev_price=189.0,
        prev_close=188.0,
        change=2.5,
        change_pct=1.33,
        timestamp=1700000000.0,
        direction="up",
    )

    assert point.ticker == "AAPL"
    assert point.price == 190.5
    assert point.direction == "up"


@pytest.mark.parametrize("impl_cls", [SimulatorMarketData, MassiveMarketData])
def test_implementations_conform_to_market_data_source_interface(impl_cls):
    assert issubclass(impl_cls, MarketDataSource)

    for method in ("start", "stop", "get_price", "get_prices", "get_all_prices", "is_ticker_supported"):
        assert hasattr(impl_cls, method)


def test_market_data_source_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        MarketDataSource()
