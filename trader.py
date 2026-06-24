import ccxt

from config import settings


def get_exchange() -> ccxt.Exchange:
    """Instantiate and return the configured CCXT exchange."""
    exchange_class = getattr(ccxt, settings.exchange_id)
    exchange = exchange_class(
        {
            "apiKey": settings.api_key,
            "secret": settings.api_secret,
            "enableRateLimit": True,
        }
    )
    return exchange


def place_order(side: str, symbol: str | None = None, amount: float | None = None) -> dict:
    """Place a buy or sell order on the configured exchange.

    Args:
        side:   "buy" or "sell"
        symbol: Trading pair, e.g. "BTC/USDT". Defaults to settings.symbol.
        amount: Base currency amount. Defaults to settings.trade_amount.

    Returns:
        The exchange order response as a dict.
    """
    exchange = get_exchange()
    symbol = symbol or settings.symbol
    amount = amount if amount is not None else settings.trade_amount
    order_type = settings.order_type

    order = exchange.create_order(symbol, order_type, side, amount)
    return order
