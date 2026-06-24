from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Exchange credentials
    exchange_id: str = "binance"
    api_key: str = ""
    api_secret: str = ""

    # Trading defaults
    symbol: str = "BTC/USDT"
    order_type: str = "market"  # "market" or "limit"
    trade_amount: float = 0.001  # base currency amount per trade

    # Webhook security
    webhook_secret: str = ""


settings = Settings()
