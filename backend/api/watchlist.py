"""Watchlist endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import queries
from market.base import MarketDataSource

from . import services
from .deps import get_conn, get_market

router = APIRouter()


class AddTickerBody(BaseModel):
    ticker: str


@router.get("/watchlist")
def get_watchlist(conn=Depends(get_conn), market: MarketDataSource = Depends(get_market)) -> list[dict]:
    result = []
    for ticker in queries.get_watchlist(conn, services.USER_ID):
        point = market.get_price(ticker)
        if point:
            result.append(
                {
                    "ticker": ticker,
                    "price": point.price,
                    "change": point.change,
                    "change_pct": point.change_pct,
                    "prev_close": point.prev_close,
                    "direction": point.direction,
                }
            )
        else:
            result.append(
                {
                    "ticker": ticker,
                    "price": 0.0,
                    "change": 0.0,
                    "change_pct": 0.0,
                    "prev_close": 0.0,
                    "direction": "flat",
                }
            )
    return result


@router.post("/watchlist")
async def add_ticker(
    body: AddTickerBody,
    conn=Depends(get_conn),
    market: MarketDataSource = Depends(get_market),
) -> dict:
    try:
        return await services.add_ticker(conn, market, body.ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/watchlist/{ticker}")
def remove_ticker(
    ticker: str,
    conn=Depends(get_conn),
    market: MarketDataSource = Depends(get_market),
) -> dict:
    try:
        return services.remove_ticker(conn, market, ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
