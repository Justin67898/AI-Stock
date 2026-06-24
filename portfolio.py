from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

DB_PATH = Path(__file__).resolve().parent / "portfolio.db"


def add_transaction(ticker: str, amount: float, buy_price: float) -> None:
    """Log a buy order in the local SQLite database."""
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("Ticker must be a non-empty string.")
    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")
    if buy_price <= 0:
        raise ValueError("Buy price must be greater than 0.")

    with _get_connection() as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO transactions (ticker, amount, buy_price, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (symbol, float(amount), float(buy_price), datetime.now(timezone.utc).isoformat()),
        )


def get_portfolio_summary() -> str:
    """
    Return a clean text summary of portfolio performance.

    Includes total invested capital, total current value, and overall gross P/L.
    """
    with _get_connection() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT ticker, SUM(amount) AS total_amount, SUM(amount * buy_price) AS invested
            FROM transactions
            GROUP BY ticker
            ORDER BY ticker
            """
        ).fetchall()

    if not rows:
        return "Portfolio Summary\n-----------------\nNo transactions recorded."

    invested_total = 0.0
    current_total = 0.0
    line_items: list[str] = []

    for ticker, total_amount, invested in rows:
        invested_amount = float(invested or 0.0)
        current_price = _get_current_price(str(ticker))
        current_value = float(total_amount) * current_price

        invested_total += invested_amount
        current_total += current_value

        line_items.append(
            f"{ticker}: shares={float(total_amount):.4f}, avg_cost=${(invested_amount/float(total_amount)):.2f}, "
            f"last=${current_price:.2f}, value=${current_value:,.2f}"
        )

    gross_pl = current_total - invested_total
    gross_pl_pct = (gross_pl / invested_total * 100.0) if invested_total > 0 else 0.0

    return (
        "Portfolio Summary\n"
        "-----------------\n"
        + "\n".join(line_items)
        + "\n-----------------\n"
        + f"Total Invested: ${invested_total:,.2f}\n"
        + f"Current Value:  ${current_total:,.2f}\n"
        + f"Gross P/L:      ${gross_pl:,.2f} ({gross_pl_pct:.2f}%)"
    )


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            amount REAL NOT NULL,
            buy_price REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _get_current_price(ticker: str) -> float:
    stock = yf.Ticker(ticker)

    fast_info = getattr(stock, "fast_info", None)
    if fast_info:
        for key in ("lastPrice", "regularMarketPrice", "previousClose"):
            try:
                value = fast_info.get(key) if hasattr(fast_info, "get") else fast_info[key]
            except Exception:
                value = None
            if value:
                return float(value)

    history = stock.history(period="1d", interval="1m")
    if history.empty:
        history = stock.history(period="5d", interval="1d")
    if history.empty:
        raise ValueError(f"Could not fetch market price for {ticker}.")

    return float(history["Close"].dropna().iloc[-1])
