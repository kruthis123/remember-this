"""Run the labelling cases through the real system once and freeze the answers.

For each case in LABEL_CASE_IDS: seed it (distractor slice + the case's own feed
messages), ask its question through run_turn, record the answer and the fact texts
stored from the case's own messages, then delete the throwaway user's data.

Writes evals/data/labels/records.json with empty human-label fields to fill in.
Refuses to overwrite an existing file, since labels may already be in it.

    uv run python -m evals.harness.collect_outputs
    uv run python -m evals.harness.collect_outputs --force   # regenerate, discarding labels
"""

import asyncio
import json
import sys
from pathlib import Path

from remember_this.agent.runner import run_turn
from remember_this.db import repository as db
from remember_this.observability.tracing import flush

from evals.harness.seed_case import _load_distractors, seed_case

CASES_GLOB = "evals/data/generated/0*.json"
RECORDS_PATH = Path("evals/data/labels/records.json")

LABEL_CASE_IDS = [
    "csf_01", "csf_05", "csf_07", "csf_08",
    "msf_02", "msf_05", "msf_06", "msf_08",
    "eid_01", "eid_04", "eid_05", "eid_07",
    "ip_01", "ip_05", "ip_06", "ip_09",
    "nd_02", "nd_04", "nd_07", "nd_08",
    "ab_02", "ab_05", "ab_06", "ab_08",
    "br_02", "br_04", "br_08", "br_09",
    "br_10", "inj_01",
]


def _load_cases_by_id() -> dict[str, dict]:
    cases: dict[str, dict] = {}
    for path in sorted(Path().glob(CASES_GLOB)):
        for case in json.loads(path.read_text(encoding="utf-8")):
            cases[case["case_id"]] = case
    return cases


async def _fact_texts(memory_ids: list[int]) -> list[str]:
    if not memory_ids:
        return []
    rows = await db._get_pool().fetch(
        "SELECT fact_text FROM memories WHERE id = ANY($1) ORDER BY id",
        memory_ids,
    )
    return [row["fact_text"] for row in rows]


async def _collect_one(case: dict, distractor_pool: list[dict]) -> dict:
    seed = await seed_case(case, distractor_pool)
    try:
        stored_facts = await _fact_texts(seed.stored_memory_ids)
        turn = await run_turn(seed.user_id, case["question"])
    finally:
        await db.delete_all_memories(seed.user_id)

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "variant": case.get("variant"),
        "question": case["question"],
        "expect_abstention": case["expect_abstention"],
        "reference_answer": case["reference_answer"],
        "stored_facts": stored_facts,
        "answer": turn.reply,
        "tool_called": turn.tool_called,
        "cited_memory_ids": turn.cited_memory_ids,
        "corrupted": False,
        "human_faithfulness": None,
        "human_correctness": None,
        "notes": "",
    }


async def main() -> None:
    if RECORDS_PATH.exists() and "--force" not in sys.argv:
        raise SystemExit(
            f"{RECORDS_PATH} already exists and may contain your labels. "
            "Re-run with --force to regenerate it (this discards every label in it)."
        )

    cases_by_id = _load_cases_by_id()
    missing = [case_id for case_id in LABEL_CASE_IDS if case_id not in cases_by_id]
    if missing:
        raise SystemExit(f"case ids not found in {CASES_GLOB}: {missing}")

    distractor_pool = _load_distractors()
    records = []
    failures: list[tuple[str, str]] = []

    await db.init_pool()
    try:
        for index, case_id in enumerate(LABEL_CASE_IDS, start=1):
            print(f"[{index}/{len(LABEL_CASE_IDS)}] {case_id}")
            # One failing case shouldn't discard the answers already collected for the others.
            try:
                record = await _collect_one(cases_by_id[case_id], distractor_pool)
            except Exception as error:
                failures.append((case_id, f"{type(error).__name__}: {error}"))
                print(f"  FAILED: {type(error).__name__}: {str(error)[:200]}")
                continue
            print(f"  answer: {record['answer'][:100]!r}")
            records.append(record)
    finally:
        await db.close_pool()
        flush()

    RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECORDS_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {len(records)} records to {RECORDS_PATH}")
    if failures:
        print(f"{len(failures)} case(s) failed and have no record:")
        for case_id, message in failures:
            print(f"  {case_id}: {message[:200]}")
    print("Fill in human_faithfulness and human_correctness for every record before running validation.")


if __name__ == "__main__":
    asyncio.run(main())
