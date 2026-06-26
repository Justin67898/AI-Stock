"""Hermes runtime loop for continuous watchlist analysis and adaptive strategy testing.

This module provides a Windows-friendly command-line interface to:
- run a 24/7 market analysis loop for a configured watchlist,
- record manual trades into the portfolio database,
- print current portfolio gross P/L summary.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
import yfinance as yf
from scipy.stats import variation

from portfolio import add_trade, get_portfolio_summary, init_db
from reflection import optimize_strategy

LOGGER = logging.getLogger("hermes_loop")
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "portfolio.db"
GOAL_PATH = ROOT / "goal.yaml"
STRATEGY_PATH = ROOT / "strategy.yaml"
PREDICTION_EVAL_SECONDS = 15 * 60

POSITIVE_NEWS_WORDS = {
    "beats",
    "surge",
    "growth",
    "upgrade",
    "record",
    "partnership",
    "profit",
    "strong",
}
NEGATIVE_NEWS_WORDS = {
    "downgrade",
    "miss",
    "lawsuit",
    "recall",
    "loss",
    "weak",
    "cut",
    "decline",
    "fall",
}


def _db_connect() -> sqlite3.Connection:
    """Create a SQLite connection tuned for concurrent Hermes operations."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@dataclass(frozen=True)
class Prediction:
    """Represents one generated market direction hypothesis."""

    ticker: str
    predicted_direction: str
    current_price: float
    confidence: float
    reason: str


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return a dict with validation and clear errors."""
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")

    with path.open("r", encoding="utf-8") as stream:
        parsed = yaml.safe_load(stream)

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected top-level mapping in {path.name}")
    return parsed


def _load_watchlist(goal: dict[str, Any]) -> list[str]:
    """Parse ticker symbols from goal.yaml asset field."""
    raw_assets = str(goal.get("asset", "")).strip()
    if not raw_assets:
        return []
    return [token.strip().upper() for token in raw_assets.split(",") if token.strip()]


def _ensure_tables() -> None:
    """Ensure required SQLite tables exist for loop and reflection state tracking."""
    init_db()
    with _db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL NOT NULL,
                price REAL,
                pnl_pct REAL DEFAULT 0,
                entry_time TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                predicted_direction TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL,
                predicted_price REAL NOT NULL,
                predicted_at TEXT NOT NULL,
                evaluated INTEGER NOT NULL DEFAULT 0,
                outcome TEXT,
                realized_return REAL
            )
            """
        )
        conn.commit()


def _latest_price(ticker: str) -> float:
    """Fetch current best-effort price for ticker using yfinance."""
    stock = yf.Ticker(ticker)

    fast_info = getattr(stock, "fast_info", None)
    if fast_info:
        for key in ("lastPrice", "regularMarketPrice", "previousClose"):
            try:
                value = fast_info.get(key) if hasattr(fast_info, "get") else fast_info[key]
            except Exception:
                value = None
            if value:
                return float(value)

    history = stock.history(period="2d", interval="1m")
    if history.empty:
        history = stock.history(period="5d", interval="1d")
    if history.empty:
        raise ValueError(f"Could not retrieve price for {ticker}")
    return float(history["Close"].dropna().iloc[-1])


def _momentum_signal(ticker: str) -> float:
    """Return simple short-term momentum over approximately 15 minutes."""
    history = yf.Ticker(ticker).history(period="1d", interval="1m")
    if history.empty or len(history) < 20:
        return 0.0

    closes = history["Close"].dropna()
    if len(closes) < 20:
        return 0.0

    recent = float(closes.iloc[-1])
    baseline = float(closes.iloc[-16])
    if baseline <= 0:
        return 0.0

    return (recent - baseline) / baseline


def _news_sentiment_score(ticker: str) -> float:
    """Estimate directional sentiment from latest article titles."""
    news_items = yf.Ticker(ticker).news or []
    if not news_items:
        return 0.0

    score = 0
    for item in news_items[:10]:
        title = str(item.get("title", "")).lower()
        for word in POSITIVE_NEWS_WORDS:
            if word in title:
                score += 1
        for word in NEGATIVE_NEWS_WORDS:
            if word in title:
                score -= 1

    return float(score) / 10.0


def _build_prediction(ticker: str, strategy: dict[str, Any]) -> Prediction:
    """Build one prediction combining momentum and news-aware directional factors."""
    momentum = _momentum_signal(ticker)
    sentiment = _news_sentiment_score(ticker)
    combined_score = (momentum * 0.7) + (sentiment * 0.3)

    threshold = float(strategy.get("entry", {}).get("jump_threshold", 0.03)) / 3.0
    direction = "up" if combined_score >= 0 else "down"
    confidence = min(0.99, max(0.51, abs(combined_score) + 0.5))

    if abs(combined_score) < threshold:
        direction = "flat"

    reason = (
        f"momentum={momentum:.4f}, sentiment={sentiment:.4f}, "
        f"threshold={threshold:.4f}"
    )

    return Prediction(
        ticker=ticker,
        predicted_direction=direction,
        current_price=_latest_price(ticker),
        confidence=confidence,
        reason=reason,
    )


def _store_prediction(prediction: Prediction) -> None:
    """Persist a generated prediction for later evaluation."""
    with _db_connect() as conn:
        conn.execute(
            """
            INSERT INTO predictions
            (ticker, predicted_direction, confidence, reason, predicted_price, predicted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                prediction.ticker,
                prediction.predicted_direction,
                prediction.confidence,
                prediction.reason,
                prediction.current_price,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def _evaluate_pending_predictions() -> tuple[int, int]:
    """Evaluate unevaluated predictions and return (wins, losses) for this pass."""
    wins = 0
    losses = 0

    with _db_connect() as conn:
        rows = conn.execute(
            """
            SELECT id, ticker, predicted_direction, predicted_price, predicted_at
            FROM predictions
            WHERE evaluated = 0
            ORDER BY id ASC
            LIMIT 100
            """
        ).fetchall()

        for row in rows:
            pred_id, ticker, direction, predicted_price, predicted_at = row
            try:
                predicted_ts = datetime.fromisoformat(str(predicted_at))
            except ValueError:
                predicted_ts = datetime.now(timezone.utc)

            age_seconds = (datetime.now(timezone.utc) - predicted_ts).total_seconds()
            if age_seconds < PREDICTION_EVAL_SECONDS:
                continue

            try:
                now_price = _latest_price(str(ticker))
            except Exception as exc:
                LOGGER.warning("Could not evaluate %s prediction %s: %s", ticker, pred_id, exc)
                continue

            predicted_price_value = float(predicted_price)
            realized_return = 0.0
            if predicted_price_value > 0:
                realized_return = (now_price - predicted_price_value) / predicted_price_value

            if direction == "flat":
                outcome = "win" if abs(realized_return) < 0.003 else "loss"
            elif direction == "up":
                outcome = "win" if realized_return > 0 else "loss"
            else:
                outcome = "win" if realized_return < 0 else "loss"

            if outcome == "win":
                wins += 1
            else:
                losses += 1

            conn.execute(
                """
                UPDATE predictions
                SET evaluated = 1, outcome = ?, realized_return = ?
                WHERE id = ?
                """,
                (outcome, realized_return, pred_id),
            )

        conn.commit()

    return wins, losses


def _prediction_win_rate(window: int = 50) -> float:
    """Compute prediction win rate over the latest evaluated predictions."""
    with _db_connect() as conn:
        rows = conn.execute(
            """
            SELECT outcome
            FROM predictions
            WHERE evaluated = 1
            ORDER BY id DESC
            LIMIT ?
            """,
            (window,),
        ).fetchall()

    if not rows:
        return 0.0

    wins = sum(1 for (outcome,) in rows if outcome == "win")
    return wins / len(rows)


def _prediction_sharpe(window: int = 50) -> float:
    """Compute Sharpe ratio from recent evaluated prediction returns."""
    with _db_connect() as conn:
        rows = conn.execute(
            """
            SELECT realized_return
            FROM predictions
            WHERE evaluated = 1 AND realized_return IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (window,),
        ).fetchall()

    if not rows:
        return 0.0

    returns = [float(value) for (value,) in rows]
    if not returns or variation(returns) == 0:
        return 0.0

    avg = sum(returns) / len(returns)
    stddev = variation(returns) * avg
    if stddev == 0:
        return 0.0
    return (avg * 252.0) / (stddev * (252.0 ** 0.5))


def _best_recommendation(watchlist: list[str], strategy: dict[str, Any]) -> str:
    """Create one actionable recommendation from current prediction set."""
    predictions: list[Prediction] = []
    for ticker in watchlist:
        try:
            predictions.append(_build_prediction(ticker, strategy))
        except Exception as exc:
            LOGGER.warning("Prediction skipped for %s: %s", ticker, exc)

    if not predictions:
        return "No recommendation available (insufficient market data)."

    ranked = sorted(predictions, key=lambda p: p.confidence, reverse=True)
    top = ranked[0]

    if top.predicted_direction == "flat":
        return f"Hold: {top.ticker} is range-bound. Reason: {top.reason}"

    action = "BUY" if top.predicted_direction == "up" else "SELL/REDUCE"
    return (
        f"{action} {top.ticker} now. Confidence={top.confidence:.2f}. "
        f"Reason: {top.reason}"
    )


def run_loop(interval_seconds: int) -> None:
    """Run the continuous Hermes monitoring and adaptive evaluation loop."""
    _ensure_tables()

    goal = _load_yaml(GOAL_PATH)
    watchlist = _load_watchlist(goal)
    if not watchlist:
        raise ValueError("No tickers configured in goal.yaml 'asset' field")

    LOGGER.info("Starting Hermes loop for watchlist: %s", ", ".join(watchlist))
    LOGGER.info("Loop interval: %s seconds", interval_seconds)

    while True:
        try:
            strategy = _load_yaml(STRATEGY_PATH)
            min_sharpe = float(goal.get("min_sharpe", 1.0))

            for ticker in watchlist:
                prediction = _build_prediction(ticker, strategy)
                _store_prediction(prediction)
                LOGGER.info(
                    "Prediction | %s | %s | conf=%.2f | price=%.2f | %s",
                    prediction.ticker,
                    prediction.predicted_direction,
                    prediction.confidence,
                    prediction.current_price,
                    prediction.reason,
                )

            wins, losses = _evaluate_pending_predictions()
            if losses > 0:
                # Scientific-method style adaptation: optimize_strategy changes one variable.
                optimize_strategy()
                LOGGER.info("Losses detected (%s). Strategy adjusted by reflection.", losses)

            win_rate = _prediction_win_rate(window=50)
            sharpe = _prediction_sharpe(window=50)

            if sharpe >= min_sharpe and win_rate >= 0.55:
                recommendation = _best_recommendation(watchlist, _load_yaml(STRATEGY_PATH))
            else:
                recommendation = (
                    "No trade action yet: strategy still learning "
                    f"(win_rate_50={win_rate:.2f}, sharpe_50={sharpe:.2f}, target_sharpe={min_sharpe:.2f})."
                )

            LOGGER.info(
                "Cycle complete | wins=%s losses=%s win_rate_50=%.2f sharpe_50=%.2f | %s",
                wins,
                losses,
                win_rate,
                sharpe,
                recommendation,
            )

        except Exception as exc:
            LOGGER.exception("Hermes loop cycle failed: %s", exc)

        time.sleep(max(30, interval_seconds))


def _build_parser() -> argparse.ArgumentParser:
    """Create CLI parser for Hermes operational modes."""
    parser = argparse.ArgumentParser(description="Hermes market monitor and portfolio assistant")
    sub = parser.add_subparsers(dest="command", required=False)

    run_cmd = sub.add_parser("run", help="Run 24/7 watchlist analysis loop")
    run_cmd.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Loop interval in seconds (default: 300)",
    )

    add_trade_cmd = sub.add_parser("add-trade", help="Record a manual trade")
    add_trade_cmd.add_argument("--ticker", required=True, help="Ticker symbol, e.g. AAPL")
    add_trade_cmd.add_argument("--shares", type=float, required=True, help="Share count")
    add_trade_cmd.add_argument("--price", type=float, required=True, help="Per-share trade price")
    add_trade_cmd.add_argument(
        "--side",
        choices=["buy", "sell"],
        default="buy",
        help="Trade direction (default: buy)",
    )

    sub.add_parser("summary", help="Show portfolio gross P/L summary")

    return parser


def main() -> None:
    """CLI entry point for running Hermes workflows.

    If no command is supplied (for example in some scheduler setups), default to
    the continuous run mode with a configurable interval.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    )

    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        args.command = "run"
        args.interval = int(os.getenv("HERMES_DEFAULT_INTERVAL", "300"))

    if args.command == "run":
        run_loop(interval_seconds=args.interval)
        return

    if args.command == "add-trade":
        add_trade(ticker=args.ticker, shares=args.shares, price=args.price, side=args.side)
        print(
            f"Recorded {args.side.upper()} trade: {args.ticker.upper()} "
            f"shares={args.shares} price=${args.price:.2f}"
        )
        return

    if args.command == "summary":
        print(get_portfolio_summary())
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
