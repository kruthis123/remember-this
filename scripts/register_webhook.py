"""One-off: register the webhook URL with Telegram.

    uv run python -m scripts.register_webhook https://your-service-url.run.app <path-token>
"""

import asyncio
import sys

import httpx

from remember_this.config import get_settings


async def main() -> None:
    if len(sys.argv) != 3:
        print("usage: register_webhook.py <base_url> <secret_path_token>")
        sys.exit(1)
    base_url, secret_path_token = sys.argv[1], sys.argv[2]

    settings = get_settings()
    telegram_url = f"https://api.telegram.org/bot{settings.telegram_bot_token.get_secret_value()}/setWebhook"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            telegram_url,
            json={
                "url": f"{base_url}/webhook/{secret_path_token}",
                "secret_token": settings.telegram_webhook_secret.get_secret_value(),
            },
        )
        response.raise_for_status()
        print(response.json())


if __name__ == "__main__":
    asyncio.run(main())
