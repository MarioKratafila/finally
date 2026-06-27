"""Server-Sent Events stream of live price updates."""

import asyncio
import dataclasses
import json

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from market.base import MarketDataSource

from .deps import get_market

router = APIRouter()

PUSH_INTERVAL_SECONDS = 0.5


@router.get("/stream/prices")
async def stream_prices(
    request: Request, market: MarketDataSource = Depends(get_market)
):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            for point in market.get_all_prices().values():
                yield {"data": json.dumps(dataclasses.asdict(point))}
            await asyncio.sleep(PUSH_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())
