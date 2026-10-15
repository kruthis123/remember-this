"""Re-run specific (strict, relaxed) pairs multiple times each, to tell a real
threshold effect apart from run-to-run noise on a 61-case dataset.

    uv run python -m evals.harness.sweep_repeat
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PAIRS = [(0.60, 0.45), (0.50, 0.35)]
REPEATS = 3

OUT_DIR = Path("evals/data/results/sweep_repeat")


def _run_one(strict: float, relaxed: float, attempt: int) -> dict:
    out_path = OUT_DIR / f"strict_{strict}_relaxed_{relaxed}_run{attempt}.json"
    env = os.environ.copy()
    env["STRICT_THRESHOLD"] = str(strict)
    env["RELAXED_THRESHOLD"] = str(relaxed)

    subprocess.run(
        [sys.executable, "-m", "evals.harness.run", "--out", str(out_path)],
        env=env,
        check=True,
    )
    return json.loads(out_path.read_text(encoding="utf-8"))


def _rate(results: list[dict], field: str, value) -> float | None:
    applicable = [r for r in results if r[field] is not None]
    if not applicable:
        return None
    return sum(1 for r in applicable if r[field] == value) / len(applicable)


def _mean_spread(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    return mean, max(values) - min(values)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []

    for strict, relaxed in PAIRS:
        faithful_runs, correct_runs, abstain_runs = [], [], []
        for attempt in range(1, REPEATS + 1):
            print(f"\n=== strict={strict} relaxed={relaxed} run {attempt}/{REPEATS} ===")
            results = _run_one(strict, relaxed, attempt)
            faithful_runs.append(_rate(results, "faithfulness", "faithful"))
            correct_runs.append(_rate(results, "correctness", "correct"))
            abstain_runs.append(_rate(results, "abstention_correctness", True))
        summary.append(
            {
                "strict": strict,
                "relaxed": relaxed,
                "faithful": _mean_spread(faithful_runs),
                "correct": _mean_spread(correct_runs),
                "abstain_ok": _mean_spread(abstain_runs),
                "raw": {"faithful": faithful_runs, "correct": correct_runs, "abstain_ok": abstain_runs},
            }
        )

    print(f"\n{'strict':>8} {'relaxed':>8} {'faithful':>18} {'correct':>18} {'abstain_ok':>18}")
    for row in summary:
        def fmt(pair):
            mean, spread = pair
            return f"{mean:.0%} (+/-{spread:.0%})"

        print(
            f"{row['strict']:>8} {row['relaxed']:>8} "
            f"{fmt(row['faithful']):>18} {fmt(row['correct']):>18} {fmt(row['abstain_ok']):>18}"
        )
        print(f"           raw: {row['raw']}")


if __name__ == "__main__":
    main()
