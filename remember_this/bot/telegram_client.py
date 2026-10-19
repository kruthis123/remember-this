import httpx

from remember_this.config import get_settings

_settings = get_settings()
_BASE_URL = f"https://api.telegram.org/bot{_settings.telegram_bot_token.get_secret_value()}"


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{_BASE_URL}/sendMessage", json=payload)
        response.raise_for_status()
        return response.json()


async def answer_callback_query(callback_query_id: str, text: str | None = None) -> dict:
    payload: dict = {"callback_query_id": callback_query_id}
    if text is not None:
        payload["text"] = text
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{_BASE_URL}/answerCallbackQuery", json=payload)
        response.raise_for_status()
        return response.json()
