"""Query helpers for the FinAlly SQLite database.

Every function takes an open ``sqlite3.Connection`` as its first argument and
commits its own writes. Rows are returned as plain dicts.
"""

import sqlite3
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- user profile ---------------------------------------------------------

def get_user_profile(conn: sqlite3.Connection, user_id: str = "default") -> dict:
    row = conn.execute(
        "SELECT * FROM users_profile WHERE user_id = ?", (user_id,)
    ).fetchone()
    return dict(row) if row else None


def update_user_cash(
    conn: sqlite3.Connection,
    user_id: str,
    cash_balance: float,
    realized_pnl: float | None = None,
) -> None:
    if realized_pnl is None:
        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE user_id = ?",
            (cash_balance, user_id),
        )
    else:
        conn.execute(
            "UPDATE users_profile SET cash_balance = ?, realized_pnl = ? WHERE user_id = ?",
            (cash_balance, realized_pnl, user_id),
        )
    conn.commit()


# --- watchlist ------------------------------------------------------------

def get_watchlist(conn: sqlite3.Connection, user_id: str = "default") -> list[str]:
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY rowid",
        (user_id,),
    ).fetchall()
    return [row["ticker"] for row in rows]


def add_to_watchlist(conn: sqlite3.Connection, user_id: str, ticker: str) -> None:
    conn.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, ticker, _now()),
    )
    conn.commit()


def remove_from_watchlist(conn: sqlite3.Connection, user_id: str, ticker: str) -> None:
    conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    )
    conn.commit()


def ticker_in_watchlist(conn: sqlite3.Connection, user_id: str, ticker: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()
    return row is not None


# --- positions ------------------------------------------------------------

def get_positions(conn: sqlite3.Connection, user_id: str = "default") -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM positions WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_position(conn: sqlite3.Connection, user_id: str, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()
    return dict(row) if row else None


def upsert_position(
    conn: sqlite3.Connection,
    user_id: str,
    ticker: str,
    quantity: float,
    avg_cost: float,
) -> None:
    conn.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, ticker)
        DO UPDATE SET quantity = excluded.quantity,
                      avg_cost = excluded.avg_cost,
                      updated_at = excluded.updated_at
        """,
        (str(uuid.uuid4()), user_id, ticker, quantity, avg_cost, _now()),
    )
    conn.commit()


def delete_position(conn: sqlite3.Connection, user_id: str, ticker: str) -> None:
    conn.execute(
        "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    )
    conn.commit()


# --- trades ---------------------------------------------------------------

def insert_trade(
    conn: sqlite3.Connection,
    user_id: str,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
) -> str:
    trade_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (trade_id, user_id, ticker, side, quantity, price, _now()),
    )
    conn.commit()
    return trade_id


# --- portfolio snapshots --------------------------------------------------

def insert_portfolio_snapshot(
    conn: sqlite3.Connection, user_id: str, total_value: float
) -> None:
    conn.execute(
        """
        INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), user_id, total_value, _now()),
    )
    conn.commit()


def get_portfolio_history(
    conn: sqlite3.Connection, user_id: str = "default", limit: int = 1000
) -> list[dict]:
    """Return snapshots oldest-first (chart-ready), capped at the newest ``limit``."""
    rows = conn.execute(
        """
        SELECT * FROM (
            SELECT * FROM portfolio_snapshots WHERE user_id = ?
            ORDER BY recorded_at DESC LIMIT ?
        ) ORDER BY recorded_at ASC
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


# --- chat messages --------------------------------------------------------

def insert_chat_message(
    conn: sqlite3.Connection,
    user_id: str,
    role: str,
    content: str,
    actions: str | None = None,
) -> str:
    message_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (message_id, user_id, role, content, actions, _now()),
    )
    conn.commit()
    return message_id


def get_recent_chat_messages(
    conn: sqlite3.Connection, user_id: str = "default", limit: int = 10
) -> list[dict]:
    """Return the newest ``limit`` messages in chronological order (oldest-first)."""
    rows = conn.execute(
        """
        SELECT * FROM (
            SELECT * FROM chat_messages WHERE user_id = ?
            ORDER BY created_at DESC LIMIT ?
        ) ORDER BY created_at ASC
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]
