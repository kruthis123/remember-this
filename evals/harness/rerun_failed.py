"""Re-run specific case ids and merge the results into an existing results file.

    uv run python -m evals.harness.rerun_failed evals/data/results/baseline.json ip_10 ab_04 br_04
"""

import asyncio
import json
import sys
from pathlib import Path

from remember_this.db import repository as db
from remember_this.observability.tracing import flush

from evals.harness.run import _load_all_cases, _run_one
from evals.harness.seed_case import _load_distractors


async def main() -> None:
    results_path = Path(sys.argv[1])
    case_ids = set(sys.argv[2:])

    results = json.loads(results_path.read_text(encoding="utf-8"))
    results = [r for r in results if r["case_id"] not in case_ids]

    cases_by_id = {c["case_id"]: c for c in _load_all_cases()}
    pool = _load_distractors()

    await db.init_pool()
    try:
        for case_id in case_ids:
            print(f"re-running {case_id}")
            for attempt in range(2):
                try:
                    results.append(await _run_one(cases_by_id[case_id], pool))
                    break
                except Exception as error:
                    print(f"  attempt {attempt + 1} failed: {type(error).__name__}: {error}")
    finally:
        await db.close_pool()
        flush()

    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(results)} results to {results_path}")


if __name__ == "__main__":
    asyncio.run(main())
