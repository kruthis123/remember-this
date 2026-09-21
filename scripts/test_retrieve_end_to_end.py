"""Throwaway manual test for remember_this.retrieval.search.retrieve, end to end
against the real database and embedding endpoint.

Run from the repo root:
    uv run python -m scripts.test_retrieve_end_to_end
"""

import asyncio

from remember_this.db import repository as db
from remember_this.retrieval.embeddings import embed_text
from remember_this.retrieval.search import retrieve

USER_ID = -3_000_001


async def main() -> None:
    await db.init_pool()
    try:
        [fact_embedding] = await embed_text(["Student id is ABCDEF"])
        await db.save_message_with_memories(
            user_id=USER_ID,
            raw_text="my student id is ABCDEF",
            facts=[("Student id is ABCDEF", fact_embedding)],
        )

        print("--- expect a strict-threshold hit, no retry, no relevance check ---")
        r1 = await retrieve(USER_ID, "What is my student id?")
        print("abstain:", r1.abstain, "retry:", r1.retry_occured)
        print("matches:", [m.fact_text for m in r1.matches])
        print("relevance_verdict:", r1.relevance_verdict)

        print("\n--- expect abstain, retry happened, nothing relevant at all ---")
        r2 = await retrieve(USER_ID, "What is the capital of France?")
        print("abstain:", r2.abstain, "retry:", r2.retry_occured)
        print("matches:", r2.matches)
        print("relevance_verdict:", r2.relevance_verdict)

        await db.delete_all_memories(USER_ID)
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
