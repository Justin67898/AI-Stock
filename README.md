# AI-Stock

Local trading toolkit with two execution modes:
1. FastAPI webhook service for TradingView-style alerts and CCXT order placement.
2. Hermes loop CLI for continuous stock watchlist analysis, prediction scoring, and strategy reflection.

## What Is In This Repo

- main.py: FastAPI app with /, /health, and /webhook endpoints.
- trader.py: CCXT exchange initialization and market order execution.
- config.py: Environment and strategy config loading.
- hermes_loop.py: Continuous analysis loop with CLI commands: run, add-trade, summary.
- portfolio.py: SQLite trade/transaction storage and portfolio summary utilities.
- reflection.py: Strategy tuning based on recent trade outcomes.
- goal.yaml: Watchlist and target constraints.
- strategy.yaml: Strategy parameters that reflection can adjust.
- run_hermes.ps1: Windows helper script to launch Hermes loop.

## Requirements

- Python 3.11+
- A virtual environment (.venv recommended)
- Dependencies in requirements.txt

Install:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Environment Setup

Create a .env file in the project root:

```dotenv
EXCHANGE_NAME=bybit
API_KEY=your_api_key
API_SECRET=your_api_secret
TESTNET=true
MARKET_TYPE=future
WEBHOOK_PASSPHRASE=CHANGE_ME_TO_A_STRONG_SECRET
```

Notes:
1. TESTNET=true is recommended while testing.
2. WEBHOOK_PASSPHRASE must match incoming webhook payloads.

## Mode 1: Run FastAPI Webhook Service

Start API server:

```powershell
uvicorn main:app --reload --port 8000
```

Endpoints:
1. GET /
2. GET /health
3. POST /webhook

Webhook JSON example:

```json
{
  "passphrase": "CHANGE_ME_TO_A_STRONG_SECRET",
  "ticker": "BTC/USDT",
  "action": "BUY",
  "amount": 0.001
}
```

Expected webhook fields:
1. passphrase: must equal WEBHOOK_PASSPHRASE.
2. ticker: symbol/pair string.
3. action: BUY or SELL.
4. amount: numeric value > 0.

## Mode 2: Run Hermes Loop

Hermes CLI commands:

```powershell
python hermes_loop.py run --interval 300
python hermes_loop.py add-trade --ticker AAPL --shares 10 --price 210 --side buy
python hermes_loop.py summary
```

PowerShell launcher:

```powershell
.\run_hermes.ps1 -Interval 300
```

Optional dry run:

```powershell
.\run_hermes.ps1 -Interval 300 -DryRun
```

Scheduler compatibility:
1. If hermes_loop.py is invoked without a subcommand, it defaults to run.
2. Interval defaults to 300 seconds, or HERMES_DEFAULT_INTERVAL if set.

## Data Files

- SQLite database: portfolio.db (created automatically).
- Watchlist and constraints: goal.yaml.
- Adaptive strategy settings: strategy.yaml.

## Safety

1. Never commit .env or API secrets.
2. Keep TESTNET=true until you have validated the full flow.
3. Confirm symbol format expected by your chosen CCXT exchange.

## Quick Troubleshooting

1. Error: missing required command
    - Use python hermes_loop.py run or run_hermes.ps1.
    - If your scheduler runs the script directly, current CLI now defaults to run.
2. Exchange order failures
    - Check API credentials, symbol format, and TESTNET support for your exchange.
3. Empty or weak predictions
    - Verify internet access for yfinance data and goal.yaml asset tickers.
