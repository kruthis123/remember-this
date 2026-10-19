from remember_this.bot import telegram_client
from remember_this.bot.keyboards import forget_confirmation_keyboard, parse_forget_callback
from remember_this.db.repository import delete_all_memories

START_TEXT = (
    "Hi! I'm a memory bot. Tell me a fact in plain English and I'll remember it "
    "(\"my student id is ABCDEF\"). Ask me about it later and I'll answer from what "
    "you've told me, or say plainly if I have nothing on that topic.\n\n"
    "Send /help for more, or /forget to erase everything I have on you."
)

HELP_TEXT = (
    "Just write naturally -- a statement is stored, a question is answered from what "
    "you've stored.\n\n"
    "/forget deletes all of your stored memories, after you confirm.\n\n"
    "Privacy: this bot is open to anyone, not restricted to any particular group. Your "
    "messages and my answers are sent to a third-party observability tool (Langfuse) and "
    "kept there for about a month to help diagnose problems. /forget deletes your stored "
    "memories but does not remove that diagnostic history."
)


async def handle_start(chat_id: int) -> None:
    await telegram_client.send_message(chat_id, START_TEXT)


async def handle_help(chat_id: int) -> None:
    await telegram_client.send_message(chat_id, HELP_TEXT)


async def handle_forget(chat_id: int, user_id: int) -> None:
    await telegram_client.send_message(
        chat_id,
        "This deletes all of your stored memories. Are you sure?",
        reply_markup=forget_confirmation_keyboard(user_id),
    )


async def handle_forget_callback(callback_query: dict) -> None:
    callback_query_id = callback_query["id"]
    sender_id = callback_query["from"]["id"]
    chat_id = callback_query["message"]["chat"]["id"]

    parsed = parse_forget_callback(callback_query["data"])
    if parsed is None:
        await telegram_client.answer_callback_query(callback_query_id)
        return
    confirmed, claimed_user_id = parsed

    # callback_data is client-controlled; the sender's own id is the only
    # identity that can be trusted to decide whose memories get deleted.
    if claimed_user_id != sender_id:
        await telegram_client.answer_callback_query(callback_query_id, text="This button isn't yours.")
        return

    if not confirmed:
        await telegram_client.answer_callback_query(callback_query_id, text="Cancelled.")
        await telegram_client.send_message(chat_id, "Okay, nothing was deleted.")
        return

    await delete_all_memories(sender_id)
    await telegram_client.answer_callback_query(callback_query_id, text="Deleted.")
    await telegram_client.send_message(chat_id, "Done -- all of your memories are deleted.")
