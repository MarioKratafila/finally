"""Tests for the SQLite database layer, run against in-memory databases."""

import sqlite3
import time
import uuid

import pytest

from db import queries
from db.connection import DEFAULT_WATCHLIST, init_db


@pytest.fixture
def conn():
    """A freshly initialized in-memory database connection."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    yield connection
    connection.close()


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


# --- schema and seed ------------------------------------------------------

def test_init_db_creates_all_tables(conn):
    expected = {
        "users_profile",
        "watchlist",
        "positions",
        "trades",
        "portfolio_snapshots",
        "chat_messages",
    }
    assert expected <= _table_names(conn)


def test_seed_inserts_default_watchlist_and_user(conn):
    tickers = queries.get_watchlist(conn)
    assert tickers == DEFAULT_WATCHLIST
    assert len(tickers) == 10

    user_count = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
    assert user_count == 1


def test_init_db_is_idempotent_and_does_not_reseed(conn):
    init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1
    assert len(queries.get_watchlist(conn)) == 10


# --- user profile ---------------------------------------------------------

def test_get_user_profile_returns_defaults(conn):
    profile = queries.get_user_profile(conn)
    assert profile["id"] == "default"
    assert profile["user_id"] == "default"
    assert profile["cash_balance"] == 10000.0
    assert profile["realized_pnl"] == 0.0


def test_update_user_cash_persists(conn):
    queries.update_user_cash(conn, "default", 8500.25)
    profile = queries.get_user_profile(conn)
    assert profile["cash_balance"] == 8500.25
    assert profile["realized_pnl"] == 0.0


def test_update_user_cash_with_realized_pnl(conn):
    queries.update_user_cash(conn, "default", 9000.0, realized_pnl=123.45)
    profile = queries.get_user_profile(conn)
    assert profile["cash_balance"] == 9000.0
    assert profile["realized_pnl"] == 123.45


# --- watchlist ------------------------------------------------------------

def test_add_and_check_watchlist(conn):
    assert queries.ticker_in_watchlist(conn, "default", "PYPL") is False
    queries.add_to_watchlist(conn, "default", "PYPL")
    assert queries.ticker_in_watchlist(conn, "default", "PYPL") is True
    assert "PYPL" in queries.get_watchlist(conn)


def test_remove_from_watchlist(conn):
    queries.remove_from_watchlist(conn, "default", "AAPL")
    assert queries.ticker_in_watchlist(conn, "default", "AAPL") is False
    assert "AAPL" not in queries.get_watchlist(conn)


def test_duplicate_watchlist_entry_raises(conn):
    with pytest.raises(sqlite3.IntegrityError):
        queries.add_to_watchlist(conn, "default", "AAPL")


# --- positions ------------------------------------------------------------

def test_get_positions_empty_by_default(conn):
    assert queries.get_positions(conn) == []


def test_get_position_returns_none_when_absent(conn):
    assert queries.get_position(conn, "default", "AAPL") is None


def test_upsert_position_inserts_then_updates(conn):
    queries.upsert_position(conn, "default", "AAPL", 10, 190.0)
    pos = queries.get_position(conn, "default", "AAPL")
    assert pos["quantity"] == 10
    assert pos["avg_cost"] == 190.0

    queries.upsert_position(conn, "default", "AAPL", 15, 192.5)
    pos = queries.get_position(conn, "default", "AAPL")
    assert pos["quantity"] == 15
    assert pos["avg_cost"] == 192.5

    assert len(queries.get_positions(conn)) == 1


def test_delete_position(conn):
    queries.upsert_position(conn, "default", "AAPL", 10, 190.0)
    queries.delete_position(conn, "default", "AAPL")
    assert queries.get_position(conn, "default", "AAPL") is None
    assert queries.get_positions(conn) == []


# --- trades ---------------------------------------------------------------

def test_insert_trade_returns_uuid(conn):
    trade_id = queries.insert_trade(conn, "default", "AAPL", "buy", 10, 190.0)
    uuid.UUID(trade_id)  # raises if not a valid UUID
    row = conn.execute(
        "SELECT * FROM trades WHERE id = ?", (trade_id,)
    ).fetchone()
    assert row["ticker"] == "AAPL"
    assert row["side"] == "buy"
    assert row["quantity"] == 10
    assert row["price"] == 190.0


# --- portfolio snapshots --------------------------------------------------

def test_portfolio_snapshot_round_trip(conn):
    queries.insert_portfolio_snapshot(conn, "default", 10000.0)
    time.sleep(0.001)
    queries.insert_portfolio_snapshot(conn, "default", 10250.0)
    history = queries.get_portfolio_history(conn)
    assert len(history) == 2
    # Oldest-first ordering.
    assert history[0]["total_value"] == 10000.0
    assert history[1]["total_value"] == 10250.0


def test_portfolio_history_respects_limit(conn):
    for value in range(5):
        queries.insert_portfolio_snapshot(conn, "default", float(value))
        time.sleep(0.001)
    history = queries.get_portfolio_history(conn, limit=2)
    assert len(history) == 2
    # The two newest, in oldest-first order.
    assert [h["total_value"] for h in history] == [3.0, 4.0]


# --- chat messages --------------------------------------------------------

def test_insert_chat_message_returns_uuid(conn):
    message_id = queries.insert_chat_message(conn, "default", "user", "hello")
    uuid.UUID(message_id)
    row = conn.execute(
        "SELECT * FROM chat_messages WHERE id = ?", (message_id,)
    ).fetchone()
    assert row["role"] == "user"
    assert row["content"] == "hello"
    assert row["actions"] is None


def test_recent_chat_messages_order_and_limit(conn):
    contents = ["m0", "m1", "m2", "m3", "m4"]
    for content in contents:
        queries.insert_chat_message(conn, "default", "user", content)
        time.sleep(0.001)

    recent = queries.get_recent_chat_messages(conn, limit=3)
    assert [m["content"] for m in recent] == ["m2", "m3", "m4"]


def test_chat_message_stores_actions(conn):
    queries.insert_chat_message(
        conn, "default", "assistant", "done", actions='{"trades": []}'
    )
    recent = queries.get_recent_chat_messages(conn, limit=1)
    assert recent[0]["actions"] == '{"trades": []}'
