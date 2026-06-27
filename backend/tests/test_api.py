"""API integration tests using FastAPI's TestClient with a temp DB and fake market."""

import time

import pytest
from fastapi.testclient import TestClient

import db.connection as connection
import main
from market.base import MarketDataSource, PricePoint

DEFAULT_TICKERS = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
]


class FakeMarket(MarketDataSource):
    """Deterministic in-memory market source for tests."""

    def __init__(self):
        self._prices = {
            t: PricePoint(
                ticker=t, price=100.0, prev_price=99.0, prev_close=98.0,
                change=2.0, change_pct=2.04, timestamp=time.time(), direction="up",
            )
            for t in DEFAULT_TICKERS
        }

    async def start(self): ...
    async def stop(self): ...

    def get_price(self, ticker):
        return self._prices.get(ticker)

    def get_prices(self, tickers):
        return {t: self._prices[t] for t in tickers if t in self._prices}

    def get_all_prices(self):
        return dict(self._prices)

    async def is_ticker_supported(self, ticker):
        return ticker in DEFAULT_TICKERS


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(main, "create_market_data_source", lambda: FakeMarket())
    with TestClient(main.app) as c:
        yield c


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_watchlist_has_ten_defaults(client):
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10
    assert {row["ticker"] for row in data} == set(DEFAULT_TICKERS)
    assert data[0]["price"] == 100.0


def test_add_duplicate_ticker_rejected(client):
    resp = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert resp.status_code == 400


def test_add_unsupported_ticker_rejected(client):
    resp = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert resp.status_code == 400


def test_remove_ticker(client):
    resp = client.delete("/api/watchlist/NFLX")
    assert resp.status_code == 200
    assert resp.json()["removed"] is True
    tickers = {row["ticker"] for row in client.get("/api/watchlist").json()}
    assert "NFLX" not in tickers


def test_portfolio_empty(client):
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cash"] == 10000.0
    assert data["total_value"] == 10000.0
    assert data["realized_pnl"] == 0.0
    assert data["positions"] == []


def test_buy_decreases_cash_and_creates_position(client):
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["price"] == 100.0
    assert body["cash_remaining"] == 9000.0

    portfolio = client.get("/api/portfolio").json()
    assert portfolio["cash"] == 9000.0
    assert len(portfolio["positions"]) == 1
    pos = portfolio["positions"][0]
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == 10
    assert pos["avg_cost"] == 100.0


def test_sell_more_than_owned_rejected(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5, "side": "buy"})
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "sell"})
    assert resp.status_code == 400


def test_buy_insufficient_cash_rejected(client):
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1000, "side": "buy"})
    assert resp.status_code == 400


def test_trade_ticker_not_in_watchlist_rejected(client):
    client.delete("/api/watchlist/NFLX")
    resp = client.post("/api/portfolio/trade", json={"ticker": "NFLX", "quantity": 1, "side": "buy"})
    assert resp.status_code == 400


def test_remove_ticker_with_position_rejected(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    resp = client.delete("/api/watchlist/AAPL")
    assert resp.status_code == 400


def test_portfolio_history(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    resp = client.get("/api/portfolio/history")
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) >= 1
    assert "total_value" in history[0]
    assert "recorded_at" in history[0]


def test_chat_mock(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "I see your portfolio" in data["message"]
    assert data["executed_trades"] == []
    assert data["failed_trades"] == []
