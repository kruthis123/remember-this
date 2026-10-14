"""Compare the judges' verdicts against your hand labels.

Reads the frozen, hand-labelled records, runs both judges on every record, writes
the verdicts to a separate file (the labels file is never modified), and reports raw
agreement and Cohen's kappa for real, corrupted, and all records.

    uv run python -m evals.harness.validate_judges
    uv run python -m evals.harness.validate_judges path/to/records.json
"""

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from evals.harness.judges import judge_correctness, judge_faithfulness

DEFAULT_RECORDS_PATH = Path("evals/data/labels/records.json")
RESULTS_PATH = Path("evals/data/labels/judge_results.json")
CONCURRENCY = 4

FAITHFULNESS_LABELS = {"faithful", "unfaithful"}
CORRECTNESS_LABELS = {"correct", "partial", "incorrect"}


def _check_labels(records: list[dict]) -> None:
    problems = []
    seen_ids = set()
    for record in records:
        case_id = record["case_id"]
        if case_id in seen_ids:
            problems.append(f"{case_id}: duplicate case_id (give corrupted copies their own id, e.g. nd_07_c1)")
        seen_ids.add(case_id)
        if record.get("human_faithfulness") not in FAITHFULNESS_LABELS:
            problems.append(f"{case_id}: human_faithfulness must be one of {sorted(FAITHFULNESS_LABELS)}")
        if record.get("human_correctness") not in CORRECTNESS_LABELS:
            problems.append(f"{case_id}: human_correctness must be one of {sorted(CORRECTNESS_LABELS)}")
    if problems:
        raise SystemExit("Fix these before validating:\n  " + "\n  ".join(problems))


def cohen_kappa(human: list[str], judge: list[str]) -> float | None:
    n = len(human)
    if n == 0:
        return None
    observed = sum(h == j for h, j in zip(human, judge)) / n
    human_counts = Counter(human)
    judge_counts = Counter(judge)
    expected = sum(
        (human_counts[label] / n) * (judge_counts[label] / n)
        for label in set(human) | set(judge)
    )
    # Both raters used a single identical label for everything: chance agreement is total,
    # so kappa is undefined rather than meaningful.
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


async def _judge_record(record: dict, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        faithfulness = await judge_faithfulness(
            record["question"], record["stored_facts"], record["answer"]
        )
        correctness = await judge_correctness(
            record["question"], record["reference_answer"], record["expect_abstention"], record["answer"]
        )
    return {
        "case_id": record["case_id"],
        "judge_faithfulness": faithfulness.verdict,
        "faithfulness_reasoning": faithfulness.reasoning,
        "unsupported_claims": faithfulness.unsupported_claims,
        "judge_correctness": correctness.verdict,
        "correctness_reasoning": correctness.reasoning,
    }


def _report(name: str, rows: list[tuple[dict, dict]], human_key: str, judge_key: str) -> None:
    print(f"\n=== {name} ===")
    for subset_name, subset in (
        ("real", [r for r in rows if not r[0]["corrupted"]]),
        ("corrupted", [r for r in rows if r[0]["corrupted"]]),
        ("all", rows),
    ):
        if not subset:
            print(f"  {subset_name:9}  (no records)")
            continue
        human = [record[human_key] for record, _ in subset]
        judge = [result[judge_key] for _, result in subset]
        agreement = sum(h == j for h, j in zip(human, judge)) / len(subset)
        kappa = cohen_kappa(human, judge)
        kappa_text = f"{kappa:.2f}" if kappa is not None else "undefined (one label used for everything)"
        print(
            f"  {subset_name:9}  n={len(subset):3d}  agreement={agreement:.0%}  kappa={kappa_text}"
            f"  human={dict(Counter(human))}  judge={dict(Counter(judge))}"
        )

    disagreements = [(record, result) for record, result in rows if record[human_key] != result[judge_key]]
    print(f"  disagreements: {len(disagreements)}")
    reasoning_key = "faithfulness_reasoning" if judge_key == "judge_faithfulness" else "correctness_reasoning"
    for record, result in disagreements:
        print(f"\n  - {record['case_id']}  human={record[human_key]}  judge={result[judge_key]}")
        print(f"    question: {record['question']}")
        print(f"    answer:   {record['answer']}")
        if record["notes"]:
            print(f"    your notes: {record['notes']}")
        print(f"    judge reasoning: {result[reasoning_key]}")


async def main() -> None:
    records_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RECORDS_PATH
    if not records_path.exists():
        raise SystemExit(f"{records_path} not found. Run `uv run python -m evals.harness.collect_outputs` first.")

    records = json.loads(records_path.read_text(encoding="utf-8"))
    _check_labels(records)

    semaphore = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(_judge_record(record, semaphore) for record in records))

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    rows = list(zip(records, results))
    _report("faithfulness", rows, "human_faithfulness", "judge_faithfulness")
    _report("correctness", rows, "human_correctness", "judge_correctness")
    print(f"\njudge verdicts written to {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
