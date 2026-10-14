"""Seed a single labelled case for eval: a random distractor slice plus the case's
own feed messages, against a throwaway user id.

Run standalone against one case file:
    uv run python -m evals.harness.seed_case evals/data/generated/01_clean_single_fact.json
"""

import asyncio
import json
import random
import sys
import zlib
from pathlib import Path

from pydantic import BaseModel

from remember_this.agent.runner import run_turn
from remember_this.db import repository as db

DISTRACTORS_PATH = Path("evals/data/generated/distractors_embedded.json")
DISTRACTOR_SLICE_SIZE = 100

# Eval user ids live in a range that can never collide with a real Telegram id.
_EVAL_USER_ID_BASE = -9_000_000_000


class SeedResult(BaseModel):
    case_id: str
    user_id: int
    distractor_count: int
    stored_memory_ids: list[int]


def _load_distractors() -> list[dict]:
    if not DISTRACTORS_PATH.exists():
        raise SystemExit(
            f"{DISTRACTORS_PATH} not found. Run "
            "`uv run python -m evals.generate.generate_distractors` then "
            "`uv run python -m evals.generate.embed_distractors` first."
        )
    return json.loads(DISTRACTORS_PATH.read_text(encoding="utf-8"))


def _case_user_id(case_id: str) -> int:
    # Deterministic per case_id, so repeated seeding of the same case lands on the same
    # throwaway user. crc32 instead of hash(): Python randomizes str hashes per process,
    # so hash() would give a different user id on every run.
    return _EVAL_USER_ID_BASE - (zlib.crc32(case_id.encode()) % 1_000_000)


async def seed_case(case: dict, distractor_pool: list[dict] | None = None) -> SeedResult:
    """Seed one case's distractor slice and feed messages. Returns the real memory
    ids created from the CASE'S OWN messages only, for inspection -- not ground
    truth to record anywhere.
    """
    if distractor_pool is None:
        distractor_pool = _load_distractors()

    user_id = _case_user_id(case["case_id"])
    await db.delete_all_memories(user_id)

    slice_ = random.sample(distractor_pool, min(DISTRACTOR_SLICE_SIZE, len(distractor_pool)))
    for note in slice_:
        await db.save_message_with_memories(
            user_id=user_id,
            raw_text=note["text"],
            facts=[(note["text"], note["embedding"])],
        )

    stored_memory_ids: list[int] = []
    for message in case.get("feed_messages", []):
        turn = await run_turn(user_id, message)
        stored_memory_ids.extend(await _memory_ids_from_last_message(user_id, message))
        print(f"  stored: {message[:70]!r} -> {turn.reply[:80]!r}")

    return SeedResult(
        case_id=case["case_id"],
        user_id=user_id,
        distractor_count=len(slice_),
        stored_memory_ids=stored_memory_ids,
    )


async def _memory_ids_from_last_message(user_id: int, raw_text: str) -> list[int]:
    """Look up which memory ids came from a specific raw message just stored.

    run_turn() doesn't return memory ids directly (its return value is the
    user-facing reply text), so this re-derives them by matching on the source
    message text. Relies on raw_text being unique within this case's seeding run,
    which holds for all seven generated categories today.
    """
    rows = await db._get_pool().fetch(
        """
        SELECT m.id
        FROM memories m
        JOIN messages msg ON msg.id = m.message_id
        WHERE m.user_id = $1 AND msg.raw_text = $2
        ORDER BY m.id
        """,
        user_id,
        raw_text,
    )
    return [row["id"] for row in rows]


async def _main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m evals.harness.seed_case <case_file.json>")

    cases = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    distractor_pool = _load_distractors()

    await db.init_pool()
    try:
        for case in cases:
            print(f"\n=== {case['case_id']} ===")
            result = await seed_case(case, distractor_pool)
            print(f"  distractors seeded: {result.distractor_count}")
            print(f"  memory ids from case's own messages: {result.stored_memory_ids}")
            print(
                "  -> diagnostic only: shows how many facts extraction produced "
                "and from which message. Not ground truth to record."
            )
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(_main())
