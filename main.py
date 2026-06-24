from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from config import settings
from trader import place_order

app = FastAPI(title="AI-Stock Trading Bot", version="0.1.0")


class WebhookPayload(BaseModel):
    secret: str
    action: str          # "buy" or "sell"
    symbol: str | None = None
    amount: float | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(payload: WebhookPayload) -> dict:
    """Receive a TradingView (or any JSON) alert and execute the trade."""
    if settings.webhook_secret and payload.secret != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    action = payload.action.lower()
    if action not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="action must be 'buy' or 'sell'")

    order = place_order(side=action, symbol=payload.symbol, amount=payload.amount)
    return {"status": "ok", "order": order}
