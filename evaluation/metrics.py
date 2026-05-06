# evaluation/metrics.py

"""Tier 1 deterministic metrics for SimBench.

This module intentionally contains only deterministic checks:
- PC: tool + required-parameter-key step matching against the gold plan.
- CRA: conflict strategy matching against the gold plan with no-conflict handling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TOOLS_SCHEMA_PATH = ROOT / "schemas" / "tools.schema.json"
_TOOLS_SCHEMA_CACHE: dict[str, Any] | None = None


def _load_tools_schema() -> dict[str, Any]:
    global _TOOLS_SCHEMA_CACHE
    if _TOOLS_SCHEMA_CACHE is not None:
        return _TOOLS_SCHEMA_CACHE

    with open(TOOLS_SCHEMA_PATH, "r", encoding="utf-8") as f:
        _TOOLS_SCHEMA_CACHE = json.load(f)
    return _TOOLS_SCHEMA_CACHE


def _required_keys(domain: str, tool_name: str) -> set[str]:
    schema = _load_tools_schema()
    domain_schema = schema.get("properties", {}).get(domain, {})
    tool_schema = domain_schema.get("properties", {}).get(tool_name, {})
    required = tool_schema.get("required", [])
    return {str(k) for k in required}


def _steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = plan.get("steps", [])
    if not isinstance(raw_steps, list):
        return []
    return [s for s in raw_steps if isinstance(s, dict)]


def _parameter_keys(step: dict[str, Any]) -> set[str]:
    params = step.get("parameters", {})

    # Legacy/free-form shape: parameters is a plain object.
    if isinstance(params, dict) and all(isinstance(k, str) for k in params.keys()) and "items" not in params:
        return set(params.keys())

    # Structured-output strict shape: parameters.items = [{key, value}, ...]
    if isinstance(params, dict):
        items = params.get("items", [])
        if isinstance(items, list):
            keys: set[str] = set()
            for row in items:
                if isinstance(row, dict) and isinstance(row.get("key"), str):
                    keys.add(row["key"])
            return keys

    return set()


def _step_matches(domain: str, agent_step: dict[str, Any], gold_step: dict[str, Any]) -> bool:
    if agent_step.get("tool") != gold_step.get("tool"):
        return False

    tool_name = str(gold_step.get("tool", ""))
    req = _required_keys(domain, tool_name)
    return req.issubset(_parameter_keys(agent_step))


def plan_correctness(task: dict[str, Any], plan: dict[str, Any], gold: dict[str, Any]) -> float:
    """PC: fraction of gold steps matched by tool name + required parameter keys."""
    gold_steps = _steps(gold)
    if not gold_steps:
        return 0.0

    candidate_steps = _steps(plan)
    used_indices: set[int] = set()
    matched = 0
    domain = str(task.get("domain", ""))

    for gold_step in gold_steps:
        found_idx = None
        for idx, agent_step in enumerate(candidate_steps):
            if idx in used_indices:
                continue
            if _step_matches(domain, agent_step, gold_step):
                found_idx = idx
                break
        if found_idx is not None:
            used_indices.add(found_idx)
            matched += 1

    return matched / len(gold_steps)


def conflict_resolution_accuracy(task: dict[str, Any], plan: dict[str, Any], gold: dict[str, Any]) -> float:
    """CRA: compare plan conflict strategy against gold with explicit no-conflict rule."""
    plan_strategy = (
        plan.get("conflict_resolution", {}).get("strategy")
        if isinstance(plan.get("conflict_resolution"), dict)
        else None
    )
    gold_strategy = (
        gold.get("conflict_resolution", {}).get("strategy")
        if isinstance(gold.get("conflict_resolution"), dict)
        else None
    )

    conflicts = task.get("conflicts")
    if conflicts is None:
        conflicts = task.get("conflict_types", [])

    has_conflicts = bool(conflicts) and conflicts != ["none"]
    if not has_conflicts:
        return 1.0 if plan_strategy == "none" else 0.0

    return 1.0 if plan_strategy == gold_strategy else 0.0


def score_tier1(task: dict[str, Any], plan: dict[str, Any], gold: dict[str, Any]) -> dict[str, float]:
    return {
        "PC": plan_correctness(task, plan, gold),
        "CRA": conflict_resolution_accuracy(task, plan, gold),
    }


def score_all(task: dict[str, Any], plan: dict[str, Any], gold: dict[str, Any]) -> dict[str, float]:
    """Backward-compatible wrapper.

    Tier 2 (PA/IS) is judged in evaluation/llm_judge.py and can be merged by
    higher-level code. Here we return deterministic metrics and default PA/IS.
    """
    tier1 = score_tier1(task, plan, gold)
    return {
        "PC": tier1["PC"],
        "PA": 0.0,
        "IS": 0.0,
        "CRA": tier1["CRA"],
    }