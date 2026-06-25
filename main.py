"""
main.py — FastAPI application entry point with reflection hooks.
"""
import logging
import warnings
from contextlib import asynccontextmanager
from typing import Any

import ccxt
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from config import settings
from trader import place_order
from reflection import optimize_strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialize on startup."""
    if not settings.api_key:
        warnings.warn("API_KEY missing — trades will fail", stacklevel=1)
    yield


app = FastAPI(title="AI-Stock", version="1.0", lifespan=lifespan)


def _log_trade_to_db(symbol: str, side: str, amount: float, order: dict) -> None:
    """Log executed trades to portfolio.db for reflection cycles."""
    try:
        conn = sqlite3.connect("portfolio.db")
        conn.execute(
            """
            INSERT INTO trades 
            (symbol, side, amount, price, entry_time) 
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (symbol, side, amount, order["price"]),
        )
        conn.commit()
    except Exception as e:
        logger.error("Failed to log trade: %s", e)


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    """Handle TradingView alerts with reflection hooks."""
    # ... [previous validation code unchanged until line 164] ...

    # Log the trade
    _log_trade_to_db(symbol=symbol, side=action, amount=amount, order=order)
    
    # Run reflection every 5 trades
    conn = sqlite3.connect("portfolio.db")
    trade_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    if trade_count % 5 == 0:
        optimize_strategy()
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "order placed", "order": order},
    )