"""
reflection.py — Optimizes strategy.yaml parameters based on recent trade performance.
"""
import sqlite3
import yaml
from datetime import datetime, timedelta
from scipy.stats import variation
from pathlib import Path
from config import settings


def calculate_sharpe_ratio(pnls: list[float]) -> float:
    """Compute annualized Sharpe ratio from PNL percentages."""
    if not pnls or variation(pnls) == 0:
        return 0.0
    
    avg_daily_return = sum(pnls) / len(pnls)
    stddev = variation(pnls) * avg_daily_return
    return (avg_daily_return * 252) / (stddev * (252 ** 0.5))


def optimize_strategy() -> None:
    """
    Optimizes ONE parameter in strategy.yaml based on last 5 trades:
    - Tightens stop_loss_pct if volatility is high
    - Adjusts jump_threshold based on hit rate
    """
    # 1. Load trade history
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT pnl_pct, entry_time 
        FROM trades 
        ORDER BY entry_time DESC 
        LIMIT 5
    """)
    trades = cursor.fetchall()
    
    if len(trades) < 5:
        return
    
    # 2. Calculate metrics
    pnls = [float(t[0]) for t in trades]
    sharpe = calculate_sharpe_ratio(pnls)
    win_rate = sum(1 for pnl in pnls if pnl > 0) / len(pnls)
    
    # 3. Load current strategy
    strategy_path = Path(__file__).parent / "strategy.yaml"
    with open(strategy_path) as f:
        strategy = yaml.safe_load(f)
    
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
    with open(strategy_path, "w") as f:
        yaml.safe_dump(strategy, f, sort_keys=False)
    
    print(f"🔍 Reflection complete: {change} | New v{strategy['version']}")