import secrets

import ccxt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from config import settings
from trader import place_order

app = FastAPI(title="AI-Stock Trading Bot", version="0.1.0")


class WebhookPayload(BaseModel):
    secret: str
    action: str          # "buy" or "sell"
    symbol: str | None = None
    amount: float | None = None

    @field_validator("secret")
    @classmethod
    def secret_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("secret must not be empty")
        return v


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(payload: WebhookPayload) -> dict:
    """Receive a TradingView (or any JSON) alert and execute the trade."""
    if settings.webhook_secret and not secrets.compare_digest(payload.secret, settings.webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    action = payload.action.lower()
    if action not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="action must be 'buy' or 'sell'")

    try:
        order = place_order(side=action, symbol=payload.symbol, amount=payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ccxt.AuthenticationError as exc:
        raise HTTPException(status_code=502, detail=f"Exchange authentication error: {exc}") from exc
    except ccxt.BaseError as exc:
        raise HTTPException(status_code=502, detail=f"Exchange error: {exc}") from exc

    return {"status": "ok", "order": order}
