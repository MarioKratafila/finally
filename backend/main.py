"""FinAlly FastAPI application."""

import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()  # loads .env from cwd (project root)

from db import get_connection, init_db
from market.factory import create_market_data_source

from api import chat, health, portfolio, stream, watchlist
from api.services import record_snapshot

SNAPSHOT_INTERVAL_SECONDS = 30


async def _snapshot_loop(market):
    """Record portfolio value every 30 seconds."""
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        try:
            conn = get_connection()
            try:
                record_snapshot(conn, market)
            finally:
                conn.close()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    market = create_market_data_source()
    app.state.market = market
    await market.start()
    snapshot_task = asyncio.create_task(_snapshot_loop(market))
    try:
        yield
    finally:
        snapshot_task.cancel()
        await market.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)

app.include_router(portfolio.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(health.router, prefix="/api")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "out")
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    @app.get("/")
    def root() -> JSONResponse:
        return JSONResponse({"status": "ok"})
