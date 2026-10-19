from datetime import datetime, timedelta, timezone

import asyncpg
import openai
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior

from remember_this.agent.runner import run_turn
from remember_this.bot import command, telegram_client
from remember_this.config import get_settings
from remember_this.db.repository import count_recent_turns, record_turn

_settings = get_settings()

NON_TEXT_REPLY = "I only understand text messages."
RATE_LIMIT_REPLY = f"You've hit the limit of {_settings.rate_limit_per_user_per_hour} messages per hour, try again shortly."

# Each entry maps an exception type to the fixed reply from the failure table
# in docs/design/phase-8-safety-and-failure.md. Order matters: checked top to
# bottom, first match wins, so put more specific types before their parents.
_FAILURE_REPLIES: list[tuple[type[Exception], str]] = [
    (UnexpectedModelBehavior, "Couldn't understand that, try rephrasing."),
    (ModelAPIError, "Can't reach the model right now, try again shortly."),
    (openai.APIError, "Can't reach the model right now, try again shortly."),
    (asyncpg.PostgresError, "Can't reach my memory right now, try again shortly."),
    (OSError, "Can't reach my memory right now, try again shortly."),
]


def _failure_reply(error: Exception) -> str:
    for error_type, reply in _FAILURE_REPLIES:
        if isinstance(error, error_type):
            return reply
    raise error


async def route_update(update: dict) -> None:
    if "callback_query" in update:
        await _route_callback(update["callback_query"])
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]

    if "text" not in message:
        await telegram_client.send_message(chat_id, NON_TEXT_REPLY)
        return

    text = message["text"]
    if text.startswith("/"):
        await _route_command(text, chat_id, user_id)
        return

    await _route_turn(text, chat_id, user_id)


async def _route_callback(callback_query: dict) -> None:
    # /forget's confirmation is the only callback query in v1.
    await command.handle_forget_callback(callback_query)


async def _route_command(text: str, chat_id: int, user_id: int) -> None:
    command_name = text.split()[0]
    if command_name == "/start":
        await command.handle_start(chat_id)
    elif command_name == "/help":
        await command.handle_help(chat_id)
    elif command_name == "/forget":
        await command.handle_forget(chat_id, user_id)
    else:
        await telegram_client.send_message(chat_id, "Unknown command. Try /help.")


async def _route_turn(text: str, chat_id: int, user_id: int) -> None:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    if await count_recent_turns(user_id, since) >= _settings.rate_limit_per_user_per_hour:
        await telegram_client.send_message(chat_id, RATE_LIMIT_REPLY)
        return
    await record_turn(user_id)

    try:
        turn = await run_turn(user_id=user_id, message=text)
    except Exception as error:
        await telegram_client.send_message(chat_id, _failure_reply(error))
        return

    await telegram_client.send_message(chat_id, turn.reply)
