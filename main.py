"""FastAPI entry point for trading webhooks and health endpoints.

This module keeps route behavior stable while applying a temporary OpenAPI
workaround for FastAPI/Starlette compatibility.
"""

from __future__ import annotations

import logging
import sqlite3
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import ccxt
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from config import settings
from reflection import optimize_strategy
from trader import place_order

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parent / "portfolio.db"


def _ensure_trade_schema() -> None:
    """Create the trades table if it does not exist yet."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL NOT NULL,
                price REAL,
                pnl_pct REAL DEFAULT 0,
                entry_time TEXT NOT NULL
            )
            """
        )
        conn.commit()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialize required runtime checks and persistence on startup."""
    _ensure_trade_schema()
    if not settings.api_key:
        warnings.warn("API_KEY missing - trades will fail", stacklevel=1)
    yield


app = FastAPI(title="AI-Stock", version="1.1", lifespan=lifespan)
app.openapi = lambda: None  # Disable docs until Starlette update


def _log_trade_to_db(symbol: str, side: str, amount: float, order: dict[str, Any]) -> None:
    """Persist executed trades to SQLite so reflection cycles can evaluate results."""
    price = order.get("price")
    if price is None:
        try:
            fills = order.get("trades") or []
            if fills and isinstance(fills, list):
                price = fills[0].get("price")
        except Exception:
            price = None

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO trades
                (symbol, side, amount, price, entry_time)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (symbol, side, amount, price),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.error("Failed to log trade to SQLite: %s", exc)


def _trade_count() -> int:
    """Return total number of recorded trades in SQLite."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT COUNT(*) FROM trades").fetchone()
    return int(row[0]) if row else 0


@app.get("/")
async def root() -> JSONResponse:
    """Provide a basic service health response for quick checks."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "service": "AI-Stock"},
    )


@app.get("/health")
async def health() -> JSONResponse:
    """Provide runtime readiness and database status information."""
    try:
        count = _trade_count()
        db_status = "ok"
    except sqlite3.Error:
        count = 0
        db_status = "error"

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ok",
            "exchange": settings.exchange_name,
            "market_type": settings.market_type,
            "testnet": settings.testnet,
            "db": db_status,
            "trade_count": count,
        },
    )


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    """Handle TradingView alerts, place orders, and trigger reflection cycles."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    if payload.get("passphrase") != settings.webhook_passphrase:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid passphrase",
        )

    symbol = str(payload.get("ticker", "")).strip().upper()
    action = str(payload.get("action", "")).strip().lower()
    raw_amount = payload.get("amount")

    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing ticker",
        )
    if action not in {"buy", "sell"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Action must be BUY or SELL",
        )

    try:
        amount = float(raw_amount)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Amount must be numeric",
        ) from exc

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Amount must be greater than 0",
        )

    try:
        order = place_order(symbol=symbol, side=action, amount=amount)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ccxt.BaseError as exc:
        logger.exception("Exchange order placement failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Exchange error: {exc}",
        ) from exc

    _log_trade_to_db(symbol=symbol, side=action, amount=amount, order=order)

    try:
        if _trade_count() % 5 == 0:
            optimize_strategy()
    except Exception as exc:
        logger.error("Reflection cycle failed: %s", exc)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "order placed", "order": order},
    )