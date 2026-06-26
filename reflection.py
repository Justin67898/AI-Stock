"""Optimize strategy.yaml parameters based on recent trade performance.

This module keeps Sharpe-ratio driven tuning intact while adding safer file I/O
for strategy updates via atomic write-and-validate behavior.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import yaml
from scipy.stats import variation


DB_PATH = Path(__file__).resolve().parent / "portfolio.db"


def _connect_db() -> sqlite3.Connection:
    """Create a SQLite connection configured to wait on short lock contention."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def calculate_sharpe_ratio(pnls: list[float]) -> float:
    """Compute annualized Sharpe ratio from PNL percentages."""
    if not pnls or variation(pnls) == 0:
        return 0.0

    avg_daily_return = sum(pnls) / len(pnls)
    stddev = variation(pnls) * avg_daily_return
    return (avg_daily_return * 252) / (stddev * (252 ** 0.5))


def _load_strategy(strategy_path: Path) -> dict[str, Any]:
    """Load and validate strategy YAML content from disk."""
    if not strategy_path.exists():
        raise FileNotFoundError(f"Missing strategy file: {strategy_path}")

    with strategy_path.open("r", encoding="utf-8") as strategy_file:
        parsed = yaml.safe_load(strategy_file)

    if not isinstance(parsed, dict):
        raise ValueError("strategy.yaml must contain a top-level mapping")
    return parsed


def _validate_strategy_schema(strategy: dict[str, Any]) -> None:
    """Validate required strategy fields before writing to disk."""
    required_keys = {"version", "entry", "stop_loss_pct", "position_size_pct"}
    missing = required_keys.difference(strategy.keys())
    if missing:
        raise ValueError(f"strategy.yaml missing required keys: {sorted(missing)}")
    if not isinstance(strategy.get("entry"), dict):
        raise ValueError("strategy.yaml 'entry' must be a mapping")


def _atomic_write_yaml(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write YAML to disk and verify parseability before replacement."""
    _validate_strategy_schema(payload)
    temp_file_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            yaml.safe_dump(payload, tmp, sort_keys=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_file_path = tmp.name

        with open(temp_file_path, "r", encoding="utf-8") as tmp_read:
            verification = yaml.safe_load(tmp_read)
            if not isinstance(verification, dict):
                raise ValueError("Atomic write verification failed for strategy.yaml")

        os.replace(temp_file_path, path)
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def optimize_strategy() -> None:
    """
    Optimizes ONE parameter in strategy.yaml based on last 5 trades:
    - Tightens stop_loss_pct if volatility is high
    - Adjusts jump_threshold based on hit rate
    """
    # 1. Load trade history
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT pnl_pct, entry_time
            FROM trades
            ORDER BY entry_time DESC
            LIMIT 5
            """
        )
        trades = cursor.fetchall()

    if len(trades) < 5:
        return

    # 2. Calculate metrics
    pnls = [float(t[0]) for t in trades]
    sharpe = calculate_sharpe_ratio(pnls)
    win_rate = sum(1 for pnl in pnls if pnl > 0) / len(pnls)

    # 3. Load current strategy
    strategy_path = Path(__file__).parent / "strategy.yaml"
    strategy = _load_strategy(strategy_path)

    # 4. Optimize ONE parameter (per goal.yaml)
    if sharpe < 1.5:
        # High risk: tighten stops
        strategy["stop_loss_pct"] = max(1.0, strategy["stop_loss_pct"] * 0.9)
        change = f"stop_loss_pct ↓ to {strategy['stop_loss_pct']:.2f}%"
    elif win_rate < 0.6:
        # Low accuracy: widen triggers
        strategy["entry"]["jump_threshold"] = min(0.05, strategy["entry"]["jump_threshold"] * 1.1)
        change = f"jump_threshold ↑ to {strategy['entry']['jump_threshold']:.3f}"
    else:
        # Good performance: increase position size
        strategy["position_size_pct"] = min(0.1, strategy["position_size_pct"] * 1.05)
        change = f"position_size_pct ↑ to {strategy['position_size_pct']:.2f}%"
    
    # 5. Save with bumped version
    strategy["version"] = f"{int(strategy['version']) + 1:02d}"
    _atomic_write_yaml(strategy_path, strategy)

    print(f"Reflection complete: {change} | New v{strategy['version']}")