"""Run the full eval suite once per (strict, relaxed) threshold pair.

Each pair runs in a fresh subprocess, since config.py's settings are cached at
import time across the whole module graph -- re-importing in-process would not
pick up a new threshold.

    uv run python -m evals.harness.sweep
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PAIRS = [
    (0.70, 0.55),
    (0.65, 0.50),  # baseline
    (0.60, 0.45),
    (0.55, 0.40),
    (0.50, 0.35),
]

OUT_DIR = Path("evals/data/results/sweep")


def _run_one(strict: float, relaxed: float) -> dict:
    out_path = OUT_DIR / f"strict_{strict}_relaxed_{relaxed}.json"
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for strict, relaxed in PAIRS:
        print(f"\n=== strict={strict} relaxed={relaxed} ===")
        results = _run_one(strict, relaxed)
        rows.append(
            {
                "strict": strict,
                "relaxed": relaxed,
                "faithful": _rate(results, "faithfulness", "faithful"),
                "correct": _rate(results, "correctness", "correct"),
                "abstention_correct": _rate(results, "abstention_correctness", True),
            }
        )

    print(f"\n{'strict':>8} {'relaxed':>8} {'faithful':>10} {'correct':>10} {'abstain_ok':>12}")
    for row in rows:
        def fmt(x):
            return f"{x:.0%}" if x is not None else "n/a"

        print(
            f"{row['strict']:>8} {row['relaxed']:>8} "
            f"{fmt(row['faithful']):>10} {fmt(row['correct']):>10} {fmt(row['abstention_correct']):>12}"
        )


if __name__ == "__main__":
    main()
