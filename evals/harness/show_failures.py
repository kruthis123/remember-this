"""Print failing cases from a results file, grouped by metric.

    uv run python -m evals.harness.show_failures evals/data/results/baseline.json
"""

import json
import sys
from pathlib import Path

BOOL_METRICS = ["verbatim_fidelity", "abstention_correctness", "attribution", "routing"]
LABEL_METRICS = {"faithfulness": "faithful", "correctness": "correct"}


def main() -> None:
    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    for metric in BOOL_METRICS:
        failures = [r for r in results if r[metric] is False]
        print(f"\n=== {metric}: {len(failures)} failing ===")
        for r in failures:
            print(f"  {r['case_id']:12} ({r['category']})")
            print(f"    answer: {r['answer']}")

    for metric, good_value in LABEL_METRICS.items():
        failures = [r for r in results if r[metric] != good_value]
        print(f"\n=== {metric}: {len(failures)} not '{good_value}' ===")
        for r in failures:
            print(f"  {r['case_id']:12} ({r['category']}) -> {r[metric]}")
            print(f"    answer: {r['answer']}")


if __name__ == "__main__":
    main()
