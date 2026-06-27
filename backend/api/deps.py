"""Shared FastAPI dependencies."""

import os
import sqlite3
from collections.abc import Iterator

from fastapi import Request

import db.connection as connection
from market.base import MarketDataSource


def get_market(request: Request) -> MarketDataSource:
    """Return the market data source stored on app.state at startup."""
    return request.app.state.market


def get_conn() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection, closing it when the request finishes.

    ``check_same_thread=False`` because FastAPI resolves this sync dependency in
    a worker thread while async routes run in the event-loop thread; the
    connection is never used concurrently within a request.
    """
    directory = os.path.dirname(connection.DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(connection.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
