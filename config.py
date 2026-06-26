"""Runtime configuration utilities for environment variables and strategy files.

This module intentionally avoids Pydantic so it is compatible with Python and
FastAPI/Starlette combinations where Pydantic v2 settings integration can fail.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class Settings:
    """Lazy settings access backed by os.getenv and on-demand file reads."""

    def __init__(self) -> None:
        """Initialize settings and preload .env values when available."""
        self._root = Path(__file__).resolve().parent
        self._env_loaded = False
        self._load_env_vars()

    def _load_env_vars(self) -> None:
        """Load variables from .env if present, without overriding existing env vars."""
        if self._env_loaded:
            return

        env_path = self._root / ".env"
        if not env_path.exists():
            self._env_loaded = True
            return

        try:
            with env_path.open("r", encoding="utf-8") as env_file:
                for raw_line in env_file:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        except OSError as exc:
            raise RuntimeError(f"Failed to read environment file: {env_path}") from exc
        finally:
            self._env_loaded = True

    @property
    def api_key(self) -> str:
        """Return API key configured in environment variables."""
        return os.getenv("API_KEY", "")

    @property
    def api_secret(self) -> str:
        """Return API secret configured in environment variables."""
        return os.getenv("API_SECRET", "")

    @property
    def webhook_passphrase(self) -> str:
        """Return webhook passphrase used to authenticate incoming alerts."""
        return os.getenv("WEBHOOK_PASSPHRASE", "CHANGE_ME_TO_A_STRONG_SECRET")

    @property
    def exchange_name(self) -> str:
        """Return exchange identifier used by CCXT."""
        return os.getenv("EXCHANGE_NAME", "binance")

    @property
    def market_type(self) -> str:
        """Return market type (spot/future/swap) for exchange order placement."""
        return os.getenv("MARKET_TYPE", "spot")

    @property
    def testnet(self) -> bool:
        """Return whether sandbox mode is enabled for the trading exchange."""
        return os.getenv("TESTNET", "true").strip().lower() in {"1", "true", "yes", "on"}

    @property
    def strategy(self) -> dict[str, Any]:
        """Load and validate strategy.yaml dynamically with clear error handling."""
        strategy_path = self._root / "strategy.yaml"
        if not strategy_path.exists():
            raise FileNotFoundError(f"Missing strategy file: {strategy_path}")

        try:
            with strategy_path.open("r", encoding="utf-8") as strategy_file:
                parsed = yaml.safe_load(strategy_file)
        except OSError as exc:
            raise RuntimeError(f"Failed to read strategy file: {strategy_path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in strategy file: {strategy_path}") from exc

        if parsed is None:
            return {}
        if not isinstance(parsed, dict):
            raise ValueError("strategy.yaml must contain a top-level mapping")
        return parsed


settings = Settings()