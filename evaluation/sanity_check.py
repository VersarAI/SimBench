"""
Sanity check for SimBench evaluation metrics.

Contract (observed from dataset):
- Gold plans: data/simbench/gold_plans/*.plan.json
- Tasks:      data/simbench/tasks/task_*.json
- A task matches a gold plan if ALL underscore-separated tokens
  from the gold plan stem are present in the task stem (order-independent).

If this fails, the metrics are broken.
"""

import json
import sys
from pathlib import Path

from evaluation import parser, metrics

TASK_DIR = Path("data/simbench/tasks")
GOLD_PLAN_DIR = Path("data/simbench/gold_plans")

# IS is a "higher is better" score: 1.0 = no interference

EXPECTED = {
    "PC": 1.0,
    "PA": 1.0,
    "IS": 1.0,   # No interference = perfect score
    "CRA": 1.0,
}

def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def score_gold_against_itself(gold_plan, task):
    # Gold plan acts as both prediction and reference
    predicted = gold_plan
    gold = gold_plan

    return {
        "PC": metrics.plan_correctness(predicted, gold, task),
        "PA": metrics.preference_adherence(predicted, gold, task),
        "IS": metrics.interference_score(predicted, gold, task),
        "CRA": metrics.conflict_resolution_accuracy(predicted, gold, task),
    }

def tokens(s: str):
    return set(s.split("_"))

def find_matching_task(gold_path: Path, task_paths):
    gold_stem = gold_path.stem.replace(".plan", "")
    gold_tokens = tokens(gold_stem)

    matches = []
    for task_path in task_paths:
        task_tokens = tokens(task_path.stem)
        if gold_tokens.issubset(task_tokens):
            matches.append(task_path)

    return matches

def main():
    gold_files = sorted(GOLD_PLAN_DIR.glob("*.plan.json"))
    task_files = sorted(TASK_DIR.glob("task_*.json"))

    if not gold_files:
        print(f"[FATAL] No gold plans found in {GOLD_PLAN_DIR}")
        sys.exit(1)

    if not task_files:
        print(f"[FATAL] No tasks found in {TASK_DIR}")
        sys.exit(1)

    failures = []

    for gold_path in gold_files:
        matches = find_matching_task(gold_path, task_files)

        if len(matches) != 1:
            failures.append(
                "\n".join([
                    f"[ERROR] Task match failure for gold plan: {gold_path.name}",
                    f"Expected exactly 1 token-matching task, found {len(matches)}",
                    "Available tasks:",
                    *[f"  - {t.name}" for t in task_files],
                ])
            )
            continue

        task_path = matches[0]
        gold_plan = load_json(gold_path)
        task = load_json(task_path)

        try:
            scores = score_gold_against_itself(gold_plan, task)
        except Exception as e:
            failures.append(
                f"[FAIL] Exception while scoring {gold_path.name}: {e}"
            )
            continue

        for metric, expected in EXPECTED.items():
            actual = scores[metric]
            if actual != expected:
                failures.append(
                    f"[FAIL] {gold_path.name} | {metric}: expected {expected}, got {actual}"
                )

    if failures:
        print("\n=== SANITY CHECK FAILURES ===")
        for f in failures:
            print(f)
        print("\n❌ Sanity check failed — metrics are incorrect.")
        sys.exit(1)

    print("✅ Sanity check passed — all gold plans score perfectly.")

if __name__ == "__main__":
    main()
