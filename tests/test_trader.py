"""Tests for trader.py — exchange factory and order placement."""
from unittest.mock import MagicMock, patch

import ccxt
import pytest


def test_get_exchange_valid(monkeypatch):
    from config import settings
    import trader

    monkeypatch.setattr(settings, "exchange_id", "binance")
    monkeypatch.setattr(settings, "api_key", "key")
    monkeypatch.setattr(settings, "api_secret", "secret")

    exchange = trader.get_exchange()
    assert isinstance(exchange, ccxt.binance)


def test_get_exchange_invalid(monkeypatch):
    from config import settings
    import trader

    monkeypatch.setattr(settings, "exchange_id", "not_a_real_exchange")
    with pytest.raises(ValueError, match="Unknown exchange"):
        trader.get_exchange()


@patch("trader.get_exchange")
def test_place_order_uses_defaults(mock_get_exchange, monkeypatch):
    from config import settings
    import trader

    monkeypatch.setattr(settings, "symbol", "ETH/USDT")
    monkeypatch.setattr(settings, "trade_amount", 0.5)
    monkeypatch.setattr(settings, "order_type", "market")

    mock_exchange = MagicMock()
    mock_exchange.create_order.return_value = {"id": "abc"}
    mock_get_exchange.return_value = mock_exchange

    result = trader.place_order("buy")
    mock_exchange.create_order.assert_called_once_with("ETH/USDT", "market", "buy", 0.5)
    assert result["id"] == "abc"


@patch("trader.get_exchange")
def test_place_order_overrides(mock_get_exchange):
    import trader

    mock_exchange = MagicMock()
    mock_exchange.create_order.return_value = {"id": "xyz"}
    mock_get_exchange.return_value = mock_exchange

    result = trader.place_order("sell", symbol="BTC/USDT", amount=0.01)
    mock_exchange.create_order.assert_called_once()
    call_args = mock_exchange.create_order.call_args[0]
    assert call_args[0] == "BTC/USDT"
    assert call_args[2] == "sell"
    assert call_args[3] == 0.01


@patch("trader.get_exchange")
def test_place_order_propagates_ccxt_error(mock_get_exchange):
    import trader

    mock_exchange = MagicMock()
    mock_exchange.create_order.side_effect = ccxt.InsufficientFunds("no funds")
    mock_get_exchange.return_value = mock_exchange

    with pytest.raises(ccxt.InsufficientFunds):
        trader.place_order("buy")
