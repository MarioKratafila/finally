"""Chat endpoint: calls the LLM and auto-executes its requested actions."""

import json
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from db import queries
from llm import chat_with_llm
from market.base import MarketDataSource

from . import services
from .deps import get_conn, get_market

router = APIRouter()


class ChatBody(BaseModel):
    message: str


def _chat_history_limit() -> int:
    return int(os.environ.get("CHAT_HISTORY_LIMIT", "10"))


def _build_context(conn, market: MarketDataSource) -> dict:
    context = services.build_portfolio(conn, market)
    watchlist = []
    for ticker in queries.get_watchlist(conn, services.USER_ID):
        point = market.get_price(ticker)
        watchlist.append(
            {
                "ticker": ticker,
                "price": point.price if point else 0.0,
                "change_pct": point.change_pct if point else 0.0,
            }
        )
    context["watchlist"] = watchlist
    return context


@router.post("/chat")
async def chat(
    body: ChatBody,
    conn=Depends(get_conn),
    market: MarketDataSource = Depends(get_market),
) -> dict:
    context = _build_context(conn, market)
    history_rows = queries.get_recent_chat_messages(conn, services.USER_ID, _chat_history_limit())
    conversation_history = [
        {"role": row["role"], "content": row["content"]} for row in history_rows
    ]

    llm_response = await chat_with_llm(body.message, context, conversation_history)

    executed_watchlist_changes = []
    failed_watchlist_changes = []
    for change in llm_response.watchlist_changes:
        try:
            if change.action == "add":
                await services.add_ticker(conn, market, change.ticker)
            elif change.action == "remove":
                services.remove_ticker(conn, market, change.ticker)
            else:
                raise ValueError(f"unknown action '{change.action}'")
            executed_watchlist_changes.append(
                {"ticker": change.ticker.upper(), "action": change.action}
            )
        except ValueError as exc:
            failed_watchlist_changes.append({"ticker": change.ticker.upper(), "error": str(exc)})

    executed_trades = []
    failed_trades = []
    for trade in llm_response.trades:
        try:
            result = services.execute_trade(conn, market, trade.ticker, trade.quantity, trade.side)
            executed_trades.append(
                {
                    "ticker": result["ticker"],
                    "side": result["side"],
                    "quantity": result["quantity"],
                    "price": result["price"],
                }
            )
        except ValueError as exc:
            failed_trades.append({"ticker": trade.ticker.upper(), "error": str(exc)})

    actions = {
        "executed_trades": executed_trades,
        "failed_trades": failed_trades,
        "executed_watchlist_changes": executed_watchlist_changes,
        "failed_watchlist_changes": failed_watchlist_changes,
    }

    queries.insert_chat_message(conn, services.USER_ID, "user", body.message)
    queries.insert_chat_message(
        conn, services.USER_ID, "assistant", llm_response.message, actions=json.dumps(actions)
    )

    return {
        "message": llm_response.message,
        "trades": [t.model_dump() for t in llm_response.trades],
        "watchlist_changes": [w.model_dump() for w in llm_response.watchlist_changes],
        **actions,
    }
