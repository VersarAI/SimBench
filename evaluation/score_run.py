from __future__ import annotations

import asyncio
from pathlib import Path

from .metrics import score_tier1
from .llm_judge import build_judge_cache_key, collect_all_sims, judge_plan
from utils.cache import Cache


ROOT = Path(__file__).resolve().parent.parent
JUDGE_CACHE_DIR = ROOT / ".cache" / "judge"


def _has_steps(plan: dict) -> bool:
    steps = plan.get("steps", [])
    return isinstance(steps, list) and len(steps) > 0


def _has_active_sims(task: dict) -> bool:
    active = task.get("active_sims", [])
    return isinstance(active, list) and len(active) > 0


def _run_judge(task: dict, plan: dict) -> dict | None:
    sims_dir = ROOT / "data" / "simbench" / "users"
    active_sims, all_sims = collect_all_sims(task, sims_dir)
    cache = Cache(JUDGE_CACHE_DIR)
    cache_key = build_judge_cache_key(task, active_sims, all_sims, plan)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    judged = asyncio.run(judge_plan(task, active_sims, all_sims, plan))
    if judged is not None:
        cache.set(cache_key, judged)
    return judged


def score_run(
    task: dict,
    plan: dict,
    gold: dict,
    judge_scores: dict[str, float] | None = None,
) -> dict[str, float | None]:
    """Return combined scores with deterministic tier always present.

    Tier 1:
    - PC, CRA from evaluation.metrics

    Tier 2:
    - PA, IS from evaluation.llm_judge (optional via judge_scores)
    """
    tier1 = score_tier1(task, plan, gold)
    pa: float | None = None
    is_: float | None = None

    # Explicit scores passed by caller take precedence.
    if judge_scores is not None:
        pa = float(judge_scores["PA"]) if judge_scores.get("PA") is not None else None
        is_ = float(judge_scores["IS"]) if judge_scores.get("IS") is not None else None
    else:
        should_call_judge = _has_steps(plan) and _has_active_sims(task)
        if should_call_judge:
            try:
                judged = _run_judge(task, plan)
                if judged is not None:
                    pa = float(judged.get("PA")) if judged.get("PA") is not None else None
                    is_ = float(judged.get("IS")) if judged.get("IS") is not None else None
            except Exception:
                # Keep nulls to distinguish judge-not-available/failure from true zero score.
                pa = None
                is_ = None

    return {
        "PC": tier1["PC"],
        "PA": pa,
        "IS": is_,
        "CRA": tier1["CRA"],
    }
