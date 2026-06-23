"""
trader.py — initialises a CCXT exchange instance and exposes helper
functions that map incoming webhook signals to executable market orders.

By default the exchange is configured to use testnet / paper-trading so
that no real funds are at risk while you are testing.
"""

import logging

import ccxt

from config import settings

logger = logging.getLogger(__name__)


def _build_exchange() -> ccxt.Exchange:
    """Create and return a configured CCXT exchange instance."""
    exchange_class = getattr(ccxt, settings.exchange_name)

    params: dict = {
        "apiKey": settings.api_key,
        "secret": settings.api_secret,
        "enableRateLimit": True,
    }

    if settings.testnet:
        # Use the market type configured in settings (default: "future").
        # Set MARKET_TYPE=spot in .env if you want to test spot trading.
        params["options"] = {"defaultType": settings.market_type}
        exchange: ccxt.Exchange = exchange_class(params)

        # Enable sandbox / testnet URL for exchanges that support it
        if exchange.has.get("sandbox"):
            exchange.set_sandbox_mode(True)
        else:
            logger.warning(
                "%s does not support sandbox mode via CCXT. "
                "Orders will target the LIVE exchange. "
                "Set TESTNET=false in .env if this is intentional.",
                settings.exchange_name,
            )
    else:
        exchange = exchange_class(params)

    return exchange


# Module-level singleton — imported by main.py
exchange = _build_exchange()


def place_order(symbol: str, side: str, amount: float) -> dict:
    """
    Place a market order on the configured exchange.

    Args:
        symbol: Trading pair in CCXT unified format, e.g. ``"BTC/USDT"``.
        side:   ``"buy"`` or ``"sell"`` (case-insensitive).
        amount: Order size in base-currency units.

    Returns:
        The raw order response dict returned by CCXT.

    Raises:
        ValueError: If ``side`` is not ``"buy"`` or ``"sell"``.
        ccxt.BaseError: On any exchange-level error.
    """
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"Invalid order side: '{side}'. Must be 'buy' or 'sell'.")

    logger.info(
        "Placing %s market order — symbol=%s  amount=%s  exchange=%s  testnet=%s",
        side.upper(),
        symbol,
        amount,
        settings.exchange_name,
        settings.testnet,
    )

    order = exchange.create_market_order(symbol, side, amount)
    logger.info("Order response: %s", order)
    return order
