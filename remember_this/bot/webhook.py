"""AWS Lambda entry point for the Telegram webhook, invoked via a Lambda
Function URL. Lambda does not support async handlers directly, so this module
owns a single persistent event loop at module scope and reuses it across warm
invocations -- asyncpg's pool is bound to the loop it was created on, so
creating a fresh loop (and pool) per invocation would mean a dead pool on
every call after the first.
"""

import asyncio
import json

from remember_this.bot.handlers import route_update
from remember_this.config import get_settings
from remember_this.db.repository import claim_update, init_pool

_settings = get_settings()
_loop = asyncio.new_event_loop()
_pool_ready = False


def _response(status_code: int, body: dict | str = "") -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body) if not isinstance(body, str) else body,
    }


async def _handle(event: dict) -> dict:
    global _pool_ready
    if not _pool_ready:
        await init_pool()
        _pool_ready = True

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if headers.get("x-telegram-bot-api-secret-token") != _settings.telegram_webhook_secret.get_secret_value():
        return _response(401, "Invalid secret token")

    update = json.loads(event.get("body") or "{}")

    if not await claim_update(update["update_id"]):
        return _response(200, {})  # already processed -- Telegram is retrying

    await route_update(update)
    return _response(200, {})


def handler(event: dict, context) -> dict:
    return _loop.run_until_complete(_handle(event))
