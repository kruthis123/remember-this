"""Throwaway manual test for remember_this.db.repository.

Not a real test suite (no pytest, no fixtures, no isolation between runs).
Just exercises every repository function once against the real Neon database
and prints pass/fail. Safe to run repeatedly: it creates its own fake user ids
and cleans up its own data at the end.

Run from the repo root:
    uv run python -m scripts.smoke_test_repository
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from remember_this.db import repository as db

# Use a user id range that will never collide with a real Telegram id in normal
# testing. Randomized so re-runs don't collide with leftovers from a crashed
# previous run either.
USER_A = -1_000_000 - random.randint(0, 999)
USER_B = -2_000_000 - random.randint(0, 999)

FAKE_DIM = 1024


def fake_vector(seed: int) -> list[float]:
    """A deterministic stand-in for a real embedding.

    IMPORTANT: this must NOT be a constant-fill vector like [seed] * FAKE_DIM.
    Cosine similarity only depends on direction, not magnitude, so [0.1]*N and
    [0.9]*N point in the exact same direction and score a perfect 1.0 against
    each other -- they are indistinguishable to `<=>`. Using a seeded random
    vector instead gives each seed a genuinely different direction; in 1024
    dimensions, two random vectors are almost orthogonal (similarity ~0) with
    very high probability, while the same seed always reproduces the same
    vector for an exact-match test.
    """
    rng = random.Random(seed)
    return [rng.gauss(0, 1) for _ in range(FAKE_DIM)]


async def expect(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


async def main() -> None:
    await db.init_pool()
    try:
        # --- save_message_with_memories: basic store + atomicity of multiple facts ---
        message_id = await db.save_message_with_memories(
            user_id=USER_A,
            raw_text="Guzman y Gomez burrito was great, exam ends Nov 30",
            facts=[
                ("The burrito place to try is Guzman y Gomez", fake_vector(1)),
                ("Final exam ends on Nov 30", fake_vector(2)),
            ],
        )
        await expect("save_message_with_memories returns an id", isinstance(message_id, int))

        # --- search_memories: exact-ish match should score near 1.0 ---
        results = await db.search_memories(
            user_id=USER_A,
            query_embedding=fake_vector(1),
            threshold=0.99,
            limit=5,
        )
        await expect("search_memories finds the matching fact", len(results) == 1)
        if results:
            await expect(
                "matched fact text is correct",
                results[0].fact_text == "The burrito place to try is Guzman y Gomez",
            )
            await expect("similarity is ~1.0 for identical vector", results[0].similarity > 0.999)

        # --- search_memories: threshold actually excludes unrelated vectors ---
        far_results = await db.search_memories(
            user_id=USER_A,
            query_embedding=fake_vector(999),  # unrelated random direction, seed never stored
            threshold=0.5,
            limit=5,
        )
        await expect("dissimilar query returns nothing above threshold", len(far_results) == 0)

        # --- isolation: a different user must not see USER_A's memories ---
        other_user_results = await db.search_memories(
            user_id=USER_B,
            query_embedding=fake_vector(1),
            threshold=0.0,  # accept anything, to prove isolation isn't just the threshold
            limit=5,
        )
        await expect("a different user id sees none of USER_A's memories", len(other_user_results) == 0)

        # --- claim_update: idempotency ---
        update_id = random.randint(10**9, 10**10)
        first_claim = await db.claim_update(update_id)
        second_claim = await db.claim_update(update_id)
        await expect("first claim of a new update_id succeeds", first_claim is True)
        await expect("second claim of the same update_id is rejected", second_claim is False)

        # --- record_turn / count_recent_turns ---
        await db.record_turn(USER_A)
        await db.record_turn(USER_A)
        since = datetime.now(timezone.utc) - timedelta(minutes=5)
        count = await db.count_recent_turns(USER_A, since)
        await expect("count_recent_turns counts the turns just recorded", count >= 2)

        long_ago = datetime.now(timezone.utc) - timedelta(days=365)
        count_all_time = await db.count_recent_turns(USER_A, long_ago)
        await expect("count_recent_turns with an old `since` still includes them", count_all_time >= count)

        # --- delete_all_memories ---
        await db.delete_all_memories(USER_A)
        post_delete_results = await db.search_memories(
            user_id=USER_A,
            query_embedding=fake_vector(1),
            threshold=0.0,
            limit=5,
        )
        await expect("delete_all_memories removes everything for that user", len(post_delete_results) == 0)

        print("\nAll checks passed.")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
