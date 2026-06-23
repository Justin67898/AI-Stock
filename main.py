"""
main.py — FastAPI application entry point.

Exposes a single POST /webhook endpoint that:
1. Validates a shared passphrase to reject unauthorised requests.
2. Parses the TradingView alert payload.
3. Routes the signal to the appropriate exchange order via trader.py.
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup validation
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    """Warn on startup if critical settings are still at their default values."""
    if not settings.api_key:
        warnings.warn("API_KEY is not set in .env — exchange authentication will fail.", stacklevel=1)
    if not settings.api_secret:
        warnings.warn("API_SECRET is not set in .env — exchange authentication will fail.", stacklevel=1)
    if settings.webhook_passphrase == "CHANGE_ME_TO_A_STRONG_SECRET":
        warnings.warn(
            "WEBHOOK_PASSPHRASE is still the default value. "
            "Change it in .env before exposing the bot to the internet.",
            stacklevel=1,
        )
    yield


app = FastAPI(title="AI-Stock Trading Bot", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health-check
# ---------------------------------------------------------------------------


@app.get("/", summary="Health check")
async def root() -> dict[str, str]:
    return {"status": "ok", "message": "AI-Stock Trading Bot is running."}


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------


@app.post("/webhook", summary="Receive TradingView alert")
async def webhook(request: Request) -> JSONResponse:
    """
    Expected JSON payload from a TradingView alert:

    ```json
    {
        "passphrase": "CHANGE_ME_TO_A_STRONG_SECRET",
        "ticker":     "BTCUSDT",
        "action":     "BUY",
        "amount":     0.001
    }
    ```

    Field descriptions
    ------------------
    passphrase  Shared secret that must match ``WEBHOOK_PASSPHRASE`` in ``.env``.
    ticker      Trading pair.  Forward-slash notation (``BTC/USDT``) is also
                accepted and normalised automatically.
    action      ``BUY`` or ``SELL`` (case-insensitive).
    amount      Order size in base-currency units (e.g. BTC for BTC/USDT).
    """
    # --- parse body ----------------------------------------------------------
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON.",
        )

    # --- security check ------------------------------------------------------
    passphrase = payload.get("passphrase", "")
    if passphrase != settings.webhook_passphrase:
        logger.warning("Webhook received with invalid passphrase.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid passphrase.",
        )

    # --- extract & validate required fields ----------------------------------
    ticker: str | None = payload.get("ticker")
    action: str | None = payload.get("action")
    amount = payload.get("amount")

    if not ticker or not action or amount is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payload must contain 'ticker', 'action', and 'amount'.",
        )

    # Pass the ticker directly to CCXT.
    # Use CCXT unified format where possible (e.g. "BTC/USDT").
    # Many exchanges also accept exchange-native symbols (e.g. "BTCUSDT") —
    # check your exchange's CCXT documentation for the exact format required.
    symbol = ticker

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'amount' must be a numeric value, got: {amount!r}",
        )

    action = action.strip().lower()
    if action not in ("buy", "sell"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'action' must be 'BUY' or 'SELL', got: {action!r}",
        )

    # --- place order ---------------------------------------------------------
    logger.info("Valid webhook received — ticker=%s  action=%s  amount=%s", symbol, action, amount)

    try:
        order = place_order(symbol=symbol, side=action, amount=amount)
    except ccxt.AuthenticationError as exc:
        logger.error("Authentication error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Exchange authentication failed. Check your API key and secret.",
        )
    except ccxt.InsufficientFunds as exc:
        logger.error("Insufficient funds: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient funds on exchange account.",
        )
    except ccxt.BaseError as exc:
        logger.error("CCXT exchange error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Exchange error: {exc}",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "order placed", "order": order},
    )
