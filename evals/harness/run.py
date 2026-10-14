"""Run every case through the real system and score it.

    uv run python -m evals.harness.run
    uv run python -m evals.harness.run --out evals/data/results/baseline.json
"""

import asyncio
import json
import sys
from pathlib import Path

from remember_this.agent.runner import run_turn
from remember_this.db import repository as db
from remember_this.observability.tracing import flush

from evals.harness import metrics
from evals.harness.judges import judge_correctness, judge_faithfulness
from evals.harness.seed_case import _load_distractors, seed_case

CASES_GLOB = "evals/data/generated/0*.json"
DEFAULT_OUT = Path("evals/data/results/latest.json")


def _load_all_cases() -> list[dict]:
    cases = []
    for path in sorted(Path().glob(CASES_GLOB)):
        cases.extend(json.loads(path.read_text(encoding="utf-8")))
    return cases


async def _fact_texts(memory_ids: list[int]) -> list[str]:
    if not memory_ids:
        return []
    rows = await db._get_pool().fetch(
        "SELECT fact_text FROM memories WHERE id = ANY($1) ORDER BY id",
        memory_ids,
    )
    return [row["fact_text"] for row in rows]


async def _run_one(case: dict, distractor_pool: list[dict]) -> dict:
    seed = await seed_case(case, distractor_pool)
    try:
        stored_facts = await _fact_texts(seed.stored_memory_ids)
        turn = await run_turn(seed.user_id, case["question"])

        faithfulness = await judge_faithfulness(case["question"], stored_facts, turn.reply)
        correctness = await judge_correctness(
            case["question"], case["reference_answer"], case["expect_abstention"], turn.reply
        )
        attribution = await metrics.attribution(turn)
    finally:
        await db.delete_all_memories(seed.user_id)

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "answer": turn.reply,
        "tool_called": turn.tool_called,
        "cited_memory_ids": turn.cited_memory_ids,
        "verbatim_fidelity": metrics.verbatim_fidelity(case, turn),
        "abstention_correctness": metrics.abstention_correctness(case, turn),
        "attribution": attribution,
        "routing": metrics.routing(turn),
        "faithfulness": faithfulness.verdict,
        "correctness": correctness.verdict,
    }


def _rate(results: list[dict], field: str, value) -> str:
    applicable = [r for r in results if r[field] is not None]
    if not applicable:
        return "n/a"
    hits = sum(1 for r in applicable if r[field] == value)
    return f"{hits}/{len(applicable)} ({hits / len(applicable):.0%})"


def _print_summary(results: list[dict]) -> None:
    print(f"\ncases run: {len(results)}")
    print(f"faithful:            {_rate(results, 'faithfulness', 'faithful')}")
    print(f"correct:             {_rate(results, 'correctness', 'correct')}")
    print(f"verbatim fidelity:   {_rate(results, 'verbatim_fidelity', True)}")
    print(f"abstention correct:  {_rate(results, 'abstention_correctness', True)}")
    print(f"attribution ok:      {_rate(results, 'attribution', True)}")
    print(f"routing ok:          {_rate(results, 'routing', True)}")


async def main() -> None:
    out_path = DEFAULT_OUT
    if "--out" in sys.argv:
        out_path = Path(sys.argv[sys.argv.index("--out") + 1])

    cases = _load_all_cases()
    distractor_pool = _load_distractors()
    results = []
    failures = []

    await db.init_pool()
    try:
        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case['case_id']}")
            # The answer/relevance agents occasionally produce output that fails
            # schema validation even after their own internal retry. One retry
            # here is cheap and clears most of these transient failures.
            for attempt in range(2):
                try:
                    results.append(await _run_one(case, distractor_pool))
                    break
                except Exception as error:
                    last_error = f"{type(error).__name__}: {error}"
                    print(f"  attempt {attempt + 1} failed: {last_error[:200]}")
            else:
                failures.append((case["case_id"], last_error))
    finally:
        await db.close_pool()
        flush()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {len(results)} results to {out_path}")
    if failures:
        print(f"{len(failures)} case(s) failed:")
        for case_id, message in failures:
            print(f"  {case_id}: {message}")
    _print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
