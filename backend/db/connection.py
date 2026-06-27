"""SQLite connection and lazy initialization for the FinAlly backend."""

import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "db/finally.db")

DEFAULT_WATCHLIST = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users_profile (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    cash_balance REAL DEFAULT 10000.0,
    realized_pnl REAL DEFAULT 0.0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    ticker TEXT NOT NULL,
    added_at TEXT,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    updated_at TEXT,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    total_value REAL NOT NULL,
    recorded_at TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    actions TEXT,
    created_at TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    """Open a connection to the SQLite database with row access by name."""
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Create all tables and seed default data when the database is empty.

    Pass an existing connection (e.g. an in-memory one) to initialize it;
    otherwise a connection to DB_PATH is opened and closed internally.
    """
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        if _needs_seed(conn):
            _seed(conn)
        conn.commit()
    finally:
        if owns_conn:
            conn.close()


def _needs_seed(conn: sqlite3.Connection) -> bool:
    count = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
    return count == 0


def _seed(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users_profile (id, user_id, cash_balance, realized_pnl, created_at) "
        "VALUES ('default', 'default', 10000.0, 0.0, ?)",
        (now,),
    )
    for ticker in DEFAULT_WATCHLIST:
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), ticker, now),
        )
