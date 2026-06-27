import asyncio
from unittest.mock import MagicMock, patch

import pytest

from market.massive import MassiveMarketData


def make_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}

    def raise_for_status():
        if status_code >= 400:
            raise Exception(f"HTTP {status_code}")

    resp.raise_for_status.side_effect = raise_for_status
    return resp


def make_snapshot(ticker="AAPL", last_trade_price=192.35, prev_close=189.87, day_close=None):
    snap = {
        "ticker": ticker,
        "prevDay": {"c": prev_close},
    }
    if last_trade_price is not None:
        snap["lastTrade"] = {"p": last_trade_price}
    if day_close is not None:
        snap["day"] = {"c": day_close}
    return snap


@pytest.mark.asyncio
async def test_fetch_and_update_parses_last_trade_and_prev_close():
    mkt = MassiveMarketData(api_key="key")
    mkt.register_ticker("AAPL")

    snapshot_response = make_response(
        json_data={"status": "OK", "tickers": [make_snapshot()]}
    )

    with patch("market.massive.requests.get", return_value=snapshot_response):
        await mkt._fetch_and_update()

    point = mkt.get_price("AAPL")
    assert point is not None
    assert point.price == 192.35
    assert point.prev_close == 189.87
    assert point.change == pytest.approx(192.35 - 189.87)
    assert point.change_pct == pytest.approx((192.35 - 189.87) / 189.87 * 100)


@pytest.mark.asyncio
async def test_fetch_and_update_falls_back_to_day_close_when_no_last_trade():
    mkt = MassiveMarketData(api_key="key")
    mkt.register_ticker("AAPL")

    snap = make_snapshot(last_trade_price=None, day_close=193.10, prev_close=189.87)
    snapshot_response = make_response(json_data={"status": "OK", "tickers": [snap]})

    with patch("market.massive.requests.get", return_value=snapshot_response):
        await mkt._fetch_and_update()

    point = mkt.get_price("AAPL")
    assert point.price == 193.10


@pytest.mark.asyncio
async def test_fetch_and_update_skips_when_no_tickers_registered():
    mkt = MassiveMarketData(api_key="key")

    with patch("market.massive.requests.get") as mock_get:
        await mkt._fetch_and_update()

    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_and_update_direction_tracks_consecutive_polls():
    mkt = MassiveMarketData(api_key="key")
    mkt.register_ticker("AAPL")

    first = make_response(json_data={
        "status": "OK", "tickers": [make_snapshot(last_trade_price=190.0, prev_close=189.0)],
    })
    second = make_response(json_data={
        "status": "OK", "tickers": [make_snapshot(last_trade_price=192.0, prev_close=189.0)],
    })

    with patch("market.massive.requests.get", return_value=first):
        await mkt._fetch_and_update()
    with patch("market.massive.requests.get", return_value=second):
        await mkt._fetch_and_update()

    point = mkt.get_price("AAPL")
    assert point.prev_price == 190.0
    assert point.price == 192.0
    assert point.direction == "up"


@pytest.mark.asyncio
async def test_is_ticker_supported_true_on_ok_status():
    mkt = MassiveMarketData(api_key="key")
    response = make_response(json_data={"status": "OK"})

    with patch("market.massive.requests.get", return_value=response):
        assert await mkt.is_ticker_supported("AAPL") is True


@pytest.mark.asyncio
async def test_is_ticker_supported_false_on_404():
    mkt = MassiveMarketData(api_key="key")
    response = make_response(status_code=404)

    with patch("market.massive.requests.get", return_value=response):
        assert await mkt.is_ticker_supported("FAKE") is False


@pytest.mark.asyncio
async def test_is_ticker_supported_false_on_exception():
    mkt = MassiveMarketData(api_key="key")

    with patch("market.massive.requests.get", side_effect=Exception("network error")):
        assert await mkt.is_ticker_supported("AAPL") is False


def test_register_and_unregister_ticker():
    mkt = MassiveMarketData(api_key="key")

    mkt.register_ticker("aapl")
    mkt.register_ticker("GOOGL")
    assert mkt._tickers == {"AAPL", "GOOGL"}

    mkt.unregister_ticker("AAPL")
    assert mkt._tickers == {"GOOGL"}


@pytest.mark.asyncio
async def test_fetch_and_update_queries_only_registered_tickers():
    mkt = MassiveMarketData(api_key="key")
    mkt.register_ticker("AAPL")
    mkt.register_ticker("GOOGL")
    mkt.unregister_ticker("GOOGL")

    response = make_response(json_data={"status": "OK", "tickers": []})

    with patch("market.massive.requests.get", return_value=response) as mock_get:
        await mkt._fetch_and_update()

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["tickers"] == "AAPL"


@pytest.mark.asyncio
async def test_fetch_and_update_handles_non_ok_status_gracefully():
    mkt = MassiveMarketData(api_key="key")
    mkt.register_ticker("AAPL")

    response = make_response(json_data={"status": "ERROR", "error": "bad key"})

    with patch("market.massive.requests.get", return_value=response):
        await mkt._fetch_and_update()  # must not raise

    assert mkt.get_price("AAPL") is None


@pytest.mark.asyncio
async def test_poll_loop_continues_after_exception():
    mkt = MassiveMarketData(api_key="key", poll_interval=0.01)

    call_count = 0

    async def flaky_fetch():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated transient failure")

    with patch.object(mkt, "_fetch_and_update", side_effect=flaky_fetch):
        task = asyncio.create_task(mkt._poll_loop())
        try:
            for _ in range(50):
                if call_count >= 2:
                    break
                await asyncio.sleep(0.01)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    assert call_count >= 2  # loop survived the first exception and polled again


@pytest.mark.asyncio
async def test_start_and_stop_lifecycle():
    mkt = MassiveMarketData(api_key="key", poll_interval=10.0)

    async def noop():
        pass

    with patch.object(mkt, "_fetch_and_update", side_effect=noop):
        await mkt.start()
        assert mkt._task is not None
        await mkt.stop()

    assert mkt._task.cancelled() or mkt._task.done()


@pytest.mark.asyncio
async def test_start_does_initial_fetch_before_background_loop():
    """start() must populate the cache immediately so SSE clients connecting
    right after startup receive data, not an empty stream."""
    mkt = MassiveMarketData(api_key="key", poll_interval=60.0)
    mkt.register_ticker("AAPL")

    snapshot_response = make_response(
        json_data={"status": "OK", "tickers": [make_snapshot()]}
    )

    with patch("market.massive.requests.get", return_value=snapshot_response):
        await mkt.start()

    try:
        assert mkt.get_price("AAPL") is not None
    finally:
        await mkt.stop()
