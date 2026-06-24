# AI-Stock

A lightweight local trading bot that listens for webhook alerts (e.g. from TradingView) and executes orders on a CCXT-supported exchange.

## Stack

| Component | Library |
|-----------|---------|
| API server | FastAPI + Uvicorn |
| Exchange connectivity | CCXT |
| Configuration | pydantic-settings |

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env        # then fill in your values
```

### `.env` example

```dotenv
EXCHANGE_ID=binance
API_KEY=your_api_key
API_SECRET=your_api_secret
SYMBOL=BTC/USDT
ORDER_TYPE=market
TRADE_AMOUNT=0.001
WEBHOOK_SECRET=change_me
```

## Running

```bash
uvicorn main:app --reload --port 8000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/webhook` | Execute a trade from a JSON alert |

### Webhook payload

```json
{
  "secret": "change_me",
  "action": "buy",
  "symbol": "BTC/USDT",
  "amount": 0.001
}
```

`symbol` and `amount` are optional and fall back to the values in `.env`.
