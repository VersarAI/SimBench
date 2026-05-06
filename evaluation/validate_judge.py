from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from evaluation.llm_judge import run_gold_self_validation

def summarize(rows: list[dict[str, Any]], threshold: float) -> tuple[bool, dict[str, Any]]:
    per_task = []
    all_passed = True
    for row in rows:
        passed = bool(row.get("passed"))
        if not passed:
            all_passed = False
        per_task.append(
            {
                "task_id": row.get("task_id"),
                "PA": row.get("PA"),
                "IS": row.get("IS"),
                "threshold": threshold,
                "passed": passed,
            }
        )

    summary = {
        "threshold": threshold,
        "all_passed": all_passed,
        "results": per_task,
    }
    return all_passed, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-validate PA/IS judge on 3 gold plans.")
    parser.add_argument(
        "--data-root",
        default="data/simbench",
        help="Root directory containing tasks and gold plans."
    )
    parser.add_argument(
        "--sims-dir",
        default="data/simbench/users",
        help="Directory containing Sim definition JSON files."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Minimum PA and IS required per gold plan."
    )
    args = parser.parse_args()

    rows = asyncio.run(
        run_gold_self_validation(
            data_root=Path(args.data_root),
            sims_dir=Path(args.sims_dir),
            threshold=args.threshold,
        )
    )
    ok, report = summarize(rows, args.threshold)
    print(json.dumps(report, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
