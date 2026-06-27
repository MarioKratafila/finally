"""Portfolio endpoints: holdings, trade execution, and value history."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import queries
from market.base import MarketDataSource

from . import services
from .deps import get_conn, get_market

router = APIRouter()


class TradeBody(BaseModel):
    ticker: str
    quantity: float
    side: str


@router.get("/portfolio")
def get_portfolio(
    conn=Depends(get_conn), market: MarketDataSource = Depends(get_market)
) -> dict:
    return services.build_portfolio(conn, market)


@router.post("/portfolio/trade")
def trade(
    body: TradeBody,
    conn=Depends(get_conn),
    market: MarketDataSource = Depends(get_market),
) -> dict:
    try:
        return services.execute_trade(conn, market, body.ticker, body.quantity, body.side)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/portfolio/history")
def get_history(conn=Depends(get_conn)) -> list[dict]:
    return [
        {"total_value": row["total_value"], "recorded_at": row["recorded_at"]}
        for row in queries.get_portfolio_history(conn, services.USER_ID)
    ]
