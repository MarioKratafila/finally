"""Shared business logic used by both the REST routes and the chat auto-executor.

Functions raise ``ValueError`` on business-rule violations (insufficient cash,
unsupported ticker, etc.). Callers translate these into HTTP 400s or chat
failure entries.
"""

from market.base import MarketDataSource
from market.massive import MassiveMarketData
from db import queries

USER_ID = "default"


def _price_of(market: MarketDataSource, ticker: str) -> float | None:
    point = market.get_price(ticker)
    return point.price if point else None


def build_portfolio(conn, market: MarketDataSource) -> dict:
    """Current cash, positions enriched with live prices, and total value."""
    profile = queries.get_user_profile(conn, USER_ID)
    cash = profile["cash_balance"]
    realized_pnl = profile["realized_pnl"]

    positions = []
    positions_value = 0.0
    for row in queries.get_positions(conn, USER_ID):
        ticker = row["ticker"]
        quantity = row["quantity"]
        avg_cost = row["avg_cost"]
        price = _price_of(market, ticker)
        current_price = price if price is not None else avg_cost
        unrealized_pnl = (current_price - avg_cost) * quantity
        pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost else 0.0
        positions_value += current_price * quantity
        positions.append(
            {
                "ticker": ticker,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "unrealized_pnl": unrealized_pnl,
                "pnl_pct": pnl_pct,
            }
        )

    total_value = cash + positions_value
    return {
        "cash": cash,
        "total_value": total_value,
        "realized_pnl": realized_pnl,
        "positions": positions,
    }


def record_snapshot(conn, market: MarketDataSource) -> float:
    """Compute total portfolio value and persist a snapshot row."""
    total_value = build_portfolio(conn, market)["total_value"]
    queries.insert_portfolio_snapshot(conn, USER_ID, total_value)
    return total_value


def execute_trade(
    conn, market: MarketDataSource, ticker: str, quantity: float, side: str
) -> dict:
    """Validate and execute a market order, updating cash, positions, and trades."""
    ticker = ticker.upper()
    side = side.lower()

    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if not queries.ticker_in_watchlist(conn, USER_ID, ticker):
        raise ValueError(f"{ticker} is not on the watchlist")

    price = _price_of(market, ticker)
    if price is None:
        raise ValueError(f"No price available for {ticker}")

    profile = queries.get_user_profile(conn, USER_ID)
    cash = profile["cash_balance"]
    realized_pnl = profile["realized_pnl"]
    position = queries.get_position(conn, USER_ID, ticker)

    if side == "buy":
        cost = price * quantity
        if cash < cost:
            raise ValueError("Insufficient cash")
        old_qty = position["quantity"] if position else 0.0
        old_avg = position["avg_cost"] if position else 0.0
        new_qty = old_qty + quantity
        new_avg = (old_qty * old_avg + quantity * price) / new_qty
        queries.upsert_position(conn, USER_ID, ticker, new_qty, new_avg)
        queries.update_user_cash(conn, USER_ID, cash - cost)
    else:  # sell
        if not position or position["quantity"] < quantity:
            raise ValueError("Insufficient shares")
        avg_cost = position["avg_cost"]
        realized_pnl += (price - avg_cost) * quantity
        remaining = position["quantity"] - quantity
        if remaining > 0:
            queries.upsert_position(conn, USER_ID, ticker, remaining, avg_cost)
        else:
            queries.delete_position(conn, USER_ID, ticker)
        queries.update_user_cash(conn, USER_ID, cash + price * quantity, realized_pnl)

    trade_id = queries.insert_trade(conn, USER_ID, ticker, side, quantity, price)
    queries.insert_portfolio_snapshot(conn, USER_ID, build_portfolio(conn, market)["total_value"])

    profile = queries.get_user_profile(conn, USER_ID)
    return {
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "trade_id": trade_id,
        "cash_remaining": profile["cash_balance"],
    }


async def add_ticker(conn, market: MarketDataSource, ticker: str) -> dict:
    """Validate a ticker is supported and not already watched, then add it."""
    ticker = ticker.upper()
    if not await market.is_ticker_supported(ticker):
        raise ValueError(f"{ticker} is not supported by the active market data source")
    if queries.ticker_in_watchlist(conn, USER_ID, ticker):
        raise ValueError(f"{ticker} is already on the watchlist")

    queries.add_to_watchlist(conn, USER_ID, ticker)
    if isinstance(market, MassiveMarketData):
        market.register_ticker(ticker)
    return {"ticker": ticker}


def remove_ticker(conn, market: MarketDataSource, ticker: str) -> dict:
    """Remove a ticker from the watchlist, rejecting if an open position exists."""
    ticker = ticker.upper()
    if queries.get_position(conn, USER_ID, ticker):
        raise ValueError("Cannot remove ticker with open position")
    queries.remove_from_watchlist(conn, USER_ID, ticker)
    return {"ticker": ticker, "removed": True}
