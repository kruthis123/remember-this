"""Manual sanity check of handlers.py routing against the real agent and
database, with telegram_client mocked out so no real Telegram call is made.

    uv run python -m scripts.test_webhook_handlers
"""

import asyncio
from unittest.mock import AsyncMock, patch

from remember_this.bot import handlers
from remember_this.db import repository as db

USER_ID = 999999001
CHAT_ID = USER_ID


async def main() -> None:
    await db.init_pool()
    try:
        await db.delete_all_memories(USER_ID)

        with patch("remember_this.bot.telegram_client.send_message", new=AsyncMock()) as send, \
             patch("remember_this.bot.telegram_client.answer_callback_query", new=AsyncMock()) as answer:

            print("--- /start ---")
            await handlers.route_update({
                "update_id": 1,
                "message": {"from": {"id": USER_ID}, "chat": {"id": CHAT_ID}, "text": "/start"},
            })
            print(send.call_args)

            print("--- non-text message ---")
            send.reset_mock()
            await handlers.route_update({
                "update_id": 2,
                "message": {"from": {"id": USER_ID}, "chat": {"id": CHAT_ID}, "sticker": {}},
            })
            print(send.call_args)

            print("--- feed turn (store a fact) ---")
            send.reset_mock()
            await handlers.route_update({
                "update_id": 3,
                "message": {"from": {"id": USER_ID}, "chat": {"id": CHAT_ID}, "text": "my student id is ABCDEF"},
            })
            print(send.call_args)

            print("--- question turn (recall it) ---")
            send.reset_mock()
            await handlers.route_update({
                "update_id": 4,
                "message": {"from": {"id": USER_ID}, "chat": {"id": CHAT_ID}, "text": "what is my student id?"},
            })
            print(send.call_args)

            print("--- /forget, sends confirmation keyboard ---")
            send.reset_mock()
            await handlers.route_update({
                "update_id": 5,
                "message": {"from": {"id": USER_ID}, "chat": {"id": CHAT_ID}, "text": "/forget"},
            })
            print(send.call_args)

            print("--- /forget callback with mismatched sender id (should refuse) ---")
            answer.reset_mock()
            send.reset_mock()
            await handlers.route_update({
                "update_id": 6,
                "callback_query": {
                    "id": "cb1",
                    "from": {"id": 1},  # not USER_ID
                    "message": {"chat": {"id": CHAT_ID}},
                    "data": f"forget:confirm:{USER_ID}",
                },
            })
            print("answer:", answer.call_args, "send:", send.call_args)

            print("--- /forget callback confirmed by the real sender ---")
            answer.reset_mock()
            send.reset_mock()
            await handlers.route_update({
                "update_id": 7,
                "callback_query": {
                    "id": "cb2",
                    "from": {"id": USER_ID},
                    "message": {"chat": {"id": CHAT_ID}},
                    "data": f"forget:confirm:{USER_ID}",
                },
            })
            print("answer:", answer.call_args, "send:", send.call_args)

        print("--- duplicate update_id, via claim_update directly (webhook.py's own check) ---")
        first = await db.claim_update(998877)
        second = await db.claim_update(998877)
        print("first claim:", first, "second claim:", second)
    finally:
        await db.delete_all_memories(USER_ID)
        await db._get_pool().execute(
            "DELETE FROM processed_updates WHERE update_id = ANY($1)",
            [1, 2, 3, 4, 5, 6, 7, 998877],
        )
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
