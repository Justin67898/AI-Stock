from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Exchange credentials
    exchange_name: str = "bybit"
    api_key: str = "YOUR_API_KEY_HERE"
    api_secret: str = "YOUR_API_SECRET_HERE"

    # Set to True to use testnet/paper-trading environment
    testnet: bool = True

    # Webhook security passphrase — must match the value sent in TradingView alert JSON
    webhook_passphrase: str = "CHANGE_ME_TO_A_STRONG_SECRET"


settings = Settings()
