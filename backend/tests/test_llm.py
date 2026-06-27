"""Unit tests for the LLM integration module. No real LLM calls are made."""

import asyncio

import pytest

from llm import LLMResponse, Trade, WatchlistChange, chat_with_llm
from llm.client import MOCK_RESPONSE
from llm.prompt import build_context_message, build_system_prompt

SAMPLE_CONTEXT = {
    "cash": 5000.0,
    "total_value": 12500.0,
    "realized_pnl": 250.0,
    "positions": [
        {
            "ticker": "AAPL",
            "quantity": 10,
            "avg_cost": 190.0,
            "current_price": 200.0,
            "unrealized_pnl": 100.0,
            "pnl_pct": 5.26,
        }
    ],
    "watchlist": [
        {"ticker": "AAPL", "price": 200.0, "change_pct": 1.2},
        {"ticker": "GOOGL", "price": 175.0, "change_pct": -0.5},
    ],
}


def test_llm_response_full():
    data = {
        "message": "Buying AAPL.",
        "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
        "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
    }
    resp = LLMResponse.model_validate(data)
    assert resp.message == "Buying AAPL."
    assert len(resp.trades) == 1
    assert resp.trades[0].ticker == "AAPL"
    assert resp.trades[0].side == "buy"
    assert resp.trades[0].quantity == 10
    assert resp.watchlist_changes[0].action == "add"


def test_llm_response_minimal():
    resp = LLMResponse.model_validate({"message": "Hello."})
    assert resp.message == "Hello."
    assert resp.trades == []
    assert resp.watchlist_changes == []


def test_trade_schema():
    trade = Trade(ticker="TSLA", side="sell", quantity=2.5)
    assert trade.ticker == "TSLA"
    assert trade.side == "sell"
    assert trade.quantity == 2.5


def test_watchlist_change_schema():
    change = WatchlistChange(ticker="NFLX", action="remove")
    assert change.ticker == "NFLX"
    assert change.action == "remove"


def test_build_system_prompt():
    prompt = build_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "FinAlly" in prompt


def test_build_context_message():
    msg = build_context_message(SAMPLE_CONTEXT)
    assert isinstance(msg, str)
    assert len(msg) > 0
    assert "AAPL" in msg
    assert "5,000.00" in msg


def test_build_context_message_empty():
    msg = build_context_message(
        {"cash": 10000.0, "total_value": 10000.0, "realized_pnl": 0.0,
         "positions": [], "watchlist": []}
    )
    assert "none" in msg
    assert "empty" in msg


def test_mock_mode_returns_mock_response(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    resp = asyncio.run(chat_with_llm("hi", SAMPLE_CONTEXT, []))
    assert resp == MOCK_RESPONSE
    assert resp.trades == []
    assert resp.watchlist_changes == []
    assert "$10,000" in resp.message


@pytest.mark.asyncio
async def test_mock_mode_async(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "TRUE")
    resp = await chat_with_llm("hello", SAMPLE_CONTEXT, [])
    assert isinstance(resp, LLMResponse)
    assert resp.message == MOCK_RESPONSE.message
