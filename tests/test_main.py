"""Tests for the FastAPI webhook endpoints."""
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure no real .env is picked up during tests
os.environ.setdefault("WEBHOOK_SECRET", "testsecret")

from main import app  # noqa: E402

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _order_payload(**overrides):
    base = {
        "secret": "testsecret",
        "action": "buy",
        "symbol": "BTC/USDT",
        "amount": 0.001,
    }
    base.update(overrides)
    return base


@patch("main.place_order")
def test_webhook_buy(mock_place_order):
    mock_place_order.return_value = {"id": "123", "side": "buy"}
    response = client.post("/webhook", json=_order_payload(action="buy"))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["order"]["id"] == "123"
    mock_place_order.assert_called_once_with(side="buy", symbol="BTC/USDT", amount=0.001)


@patch("main.place_order")
def test_webhook_sell(mock_place_order):
    mock_place_order.return_value = {"id": "456", "side": "sell"}
    response = client.post("/webhook", json=_order_payload(action="sell"))
    assert response.status_code == 200
    assert response.json()["order"]["side"] == "sell"


@patch("main.place_order")
def test_webhook_optional_fields_omitted(mock_place_order):
    """symbol and amount are optional — should fall back to defaults."""
    mock_place_order.return_value = {"id": "789"}
    payload = {"secret": "testsecret", "action": "buy"}
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    mock_place_order.assert_called_once_with(side="buy", symbol=None, amount=None)


def test_webhook_wrong_secret():
    response = client.post("/webhook", json=_order_payload(secret="wrong"))
    assert response.status_code == 403


def test_webhook_empty_secret():
    response = client.post("/webhook", json=_order_payload(secret="   "))
    assert response.status_code == 422  # pydantic validation error


def test_webhook_invalid_action():
    response = client.post("/webhook", json=_order_payload(action="hold"))
    assert response.status_code == 400


@patch("main.place_order", side_effect=ValueError("Unknown exchange: 'bad'"))
def test_webhook_bad_exchange_returns_400(mock_place_order):
    response = client.post("/webhook", json=_order_payload())
    assert response.status_code == 400
    assert "Unknown exchange" in response.json()["detail"]


@patch("main.place_order")
def test_webhook_ccxt_error_returns_502(mock_place_order):
    import ccxt

    mock_place_order.side_effect = ccxt.NetworkError("timeout")
    response = client.post("/webhook", json=_order_payload())
    assert response.status_code == 502
