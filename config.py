import os
from pathlib import Path
import yaml
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    # Existing settings
    api_key: str = Field(..., env="API_KEY")
    api_secret: str = Field(..., env="API_SECRET")
    webhook_passphrase: str = Field("CHANGE_ME_TO_A_STRONG_SECRET", env="WEBHOOK_PASSPHRASE")
    exchange_name: str = Field("binance", env="EXCHANGE_NAME")
    market_type: str = Field("spot", env="MARKET_TYPE")
    testnet: bool = Field(True, env="TESTNET")
    
    # New strategy loader
    @property
    def strategy(self) -> dict:
        with open(Path(__file__).parent / "strategy.yaml") as f:
            return yaml.safe_load(f)

    class Config:
        env_file = ".env"

settings = Settings()