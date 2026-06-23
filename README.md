# AI-Stock — Lightweight Local AI Trading Bot

A zero-cost, locally-run trading bot that listens for real-time webhook signals from **TradingView** (or any HTTP client) and routes them as market orders through the **CCXT** library.  
No paid cloud infrastructure required — just your machine and a free ngrok tunnel.

---

## Features

- **FastAPI** webhook endpoint at `POST /webhook`
- **Passphrase validation** on every incoming request to block unauthorised signals
- **CCXT** integration — supports 100+ exchanges out of the box
- **Testnet / paper-trading** by default (Bybit, Binance, etc.) — no real money at risk while you test
- Configuration loaded from a local `.env` file via **pydantic-settings**

---

## File Structure

```
AI-Stock/
├── main.py          # FastAPI app & webhook handler
├── config.py        # Settings loaded from .env
├── trader.py        # CCXT exchange initialisation & order logic
├── requirements.txt # Python dependencies
├── .env             # Your secrets (never committed — see .gitignore)
└── .gitignore
```

---

## Quick Start

### 1 — Clone & install dependencies

```bash
git clone https://github.com/Justin67898/AI-Stock.git
cd AI-Stock

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2 — Configure your `.env` file

Copy the example below, paste it into a new file called `.env` in the project root, and fill in your values:

```dotenv
# .env  (never commit this file)

EXCHANGE_NAME=bybit           # Any exchange supported by CCXT
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here
TESTNET=true                  # true = paper trading, false = live trading
MARKET_TYPE=future            # spot | future | swap (default: future)

# Must match the "passphrase" field sent in every TradingView alert
WEBHOOK_PASSPHRASE=CHANGE_ME_TO_A_STRONG_SECRET
```

> **Tip:** For Bybit testnet keys, visit <https://testnet.bybit.com> → API Management.  
> For Binance testnet, visit <https://testnet.binance.vision>.

### 3 — Run the bot locally

```bash
uvicorn main:app --reload --port 8000
```

The API docs are available at <http://localhost:8000/docs>.

---

## Exposing the Bot to the Internet (for TradingView)

TradingView alerts require a **publicly reachable HTTPS URL**.  
The simplest free option is **ngrok**:

```bash
# In a second terminal (while uvicorn is running)
ngrok http 8000
```

ngrok will print a forwarding URL similar to:

```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

Use `https://abc123.ngrok-free.app/webhook` as the **Webhook URL** in your TradingView alert.

> **Note:** The free ngrok URL changes every time you restart ngrok.  
> For a stable URL, sign up for a free ngrok account and follow their instructions for a reserved domain.

---

## TradingView Alert Setup

In TradingView, create an alert and set the **Message** to the following JSON.  
Replace the values as needed:

```json
{
    "passphrase": "CHANGE_ME_TO_A_STRONG_SECRET",
    "ticker":     "{{ticker}}",
    "action":     "BUY",
    "amount":     0.001
}
```

| Field        | Description                                                  |
|--------------|--------------------------------------------------------------|
| `passphrase` | Must match `WEBHOOK_PASSPHRASE` in your `.env` file          |
| `ticker`     | Trading pair in CCXT format, e.g. `BTC/USDT` or exchange-native `BTCUSDT` |
| `action`     | `BUY` or `SELL` (case-insensitive)                           |
| `amount`     | Order size in base-currency units (e.g. BTC for a BTC pair)  |

---

## Security Notes

- Keep your `WEBHOOK_PASSPHRASE` strong and private.
- **Never** commit your `.env` file — it is excluded by `.gitignore`.
- Consider firewall rules or VPN access when moving to production.
- Always verify orders on the exchange dashboard before going live.

---

## License

MIT
