import ccxt

from config import settings

_KNOWN_EXCHANGES: frozenset[str] = frozenset(ccxt.exchanges)


def get_exchange() -> ccxt.Exchange:
    """Instantiate and return the configured CCXT exchange."""
    exchange_id = settings.exchange_id
    if exchange_id not in _KNOWN_EXCHANGES:
        raise ValueError(f"Unknown exchange: {exchange_id!r}. Must be one of the exchanges supported by CCXT.")
    exchange_class = getattr(ccxt, exchange_id)
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

    Raises:
        ValueError: If the exchange id is unknown.
        ccxt.BaseError: On exchange-level errors (auth, balance, network, …).
    """
    exchange = get_exchange()
    symbol = symbol or settings.symbol
    amount = amount if amount is not None else settings.trade_amount
    order_type = settings.order_type

    try:
        order = exchange.create_order(symbol, order_type, side, amount)
    except ccxt.BaseError:
        raise
    return order
