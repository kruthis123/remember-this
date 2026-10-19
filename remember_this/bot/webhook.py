from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request

from remember_this.bot.handlers import route_update
from remember_this.config import get_settings
from remember_this.db.repository import claim_update, close_pool, init_pool

_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook/{secret_path_token}")
async def webhook(
    secret_path_token: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if x_telegram_bot_api_secret_token != _settings.telegram_webhook_secret.get_secret_value():
        raise HTTPException(status_code=401, detail="Invalid secret token")

    update = await request.json()

    if not await claim_update(update["update_id"]):
        return {}  # already processed -- Telegram is retrying

    await route_update(update)
    return {}
