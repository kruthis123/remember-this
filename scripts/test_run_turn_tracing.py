import asyncio

from remember_this.agent.runner import hash_user_id, run_turn
from remember_this.db import repository as db
from remember_this.observability.tracing import flush, langfuse

USER_ID = -5_000_001


async def main() -> None:
    await db.init_pool()
    try:
        await db.delete_all_memories(USER_ID)

        save_reply = await run_turn(USER_ID, "My student id is ABCDEF")
        print("save reply:", save_reply)
        print("trace url:", langfuse.get_trace_url())

        search_reply = await run_turn(USER_ID, "What is my student id?")
        print("\nsearch reply:", search_reply)
        print("trace url:", langfuse.get_trace_url())

        print("\nhashed_user_id for", USER_ID, "->", hash_user_id(USER_ID))
        print("open each trace url above and confirm hashed_user_id and settings")
        print("values appear in the outer 'turn' span's metadata, and that no")
        print("raw user id appears anywhere in either trace.")

        await db.delete_all_memories(USER_ID)
    finally:
        await db.close_pool()
        flush()


if __name__ == "__main__":
    asyncio.run(main())
