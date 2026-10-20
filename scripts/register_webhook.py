"""One-off: register the webhook URL with Telegram.

    uv run python -m scripts.register_webhook https://xxxx.lambda-url.us-east-1.on.aws/
"""

import asyncio
import sys

import httpx

from remember_this.config import get_settings


async def main() -> None:
    if len(sys.argv) != 2:
        print("usage: register_webhook.py <lambda_function_url>")
        sys.exit(1)
    function_url = sys.argv[1]

    settings = get_settings()
    telegram_url = f"https://api.telegram.org/bot{settings.telegram_bot_token.get_secret_value()}/setWebhook"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            telegram_url,
            json={
                "url": function_url,
                "secret_token": settings.telegram_webhook_secret.get_secret_value(),
            },
        )
        response.raise_for_status()
        print(response.json())


if __name__ == "__main__":
    asyncio.run(main())
