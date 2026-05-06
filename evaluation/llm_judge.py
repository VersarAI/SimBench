from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any

import jsonschema
from dotenv import load_dotenv
from openai import AsyncOpenAI

MODEL_NAME = "gpt-4o"
JUDGE_SCHEMA_PATH = Path(__file__).resolve().parent / "judge_output.schema.json"
DEFAULT_DATA_ROOT = Path("data/simbench")
JUDGE_CACHE_VERSION = "judge_prompt_v1"

SYSTEM_PROMPT = (
    "You are a critical evaluator of plan quality with respect to user personas (Sims). "
    "Your primary job is to assess whether a generated plan demonstrates AWARENESS of and ADHERENCE to "
    "the active user's specific constraints, priorities, communication style, and contextual needs. "
    "Evaluate only the provided task, active Sim definitions, and plan. "
    "Do not infer hidden context; do not invent missing facts. "
    "Look for explicit evidence in plan text (step justifications, tool choices, conflict_resolution rationale) "
    "that shows the model understood and incorporated Sim details. "
    "Return strict JSON only."
)

USER_PROMPT_TEMPLATE = """You are evaluating whether the generated plan respects the active user personas (Sims) and their constraints/priorities.

ACTIVE SIMS CONTEXT:
Review these active Sims and their distinctive characteristics:
{all_sims_json}

Key aspects to check for each active Sim:
- Specific constraints (hard constraints MUST be respected; soft constraints are preferred but not mandatory)
- Stated priorities (the plan should demonstrate awareness of these when making trade-offs)
- Communication style (informally check if justifications align with this style)
- Contextual notes (recovery status, role, challenges - all should inform the plan)

SIM-AWARE PLANNING SIGNALS:
- Plan step justifications explicitly reference Sim constraints or priorities
- Trade-offs are made between conflicting Sims (e.g., "sleep priority takes precedence over availability when it conflicts")
- Specific constraints are respected (e.g., "no meetings after 9pm" is scheduled around, not violated)
- Plan acknowledges or resolves conflicts mentioned in conflict_resolution section
- Tool selections align with Sim needs (e.g., choosing fitness_scheduler respects health Sim)

GENERIC PLANNING SIGNALS (low Sim adherence):
- Steps and justifications make NO reference to Sim details
- Constraints are violated or ignored without acknowledgment
- Tool choices seem arbitrary rather than driven by Sim context
- Conflict_resolution.strategy is generic ("none") when Sims have competing priorities

Evaluate this plan with two metrics:

1) PA (Preference Adherence):
- Use ONLY active Sims and their listed constraints/priorities.
- For each active constraint in pa_constraints, assign verdict yes/partially/no and score 1.0/0.5/0.0.
- Include one concise rationale per constraint in pa_breakdown that explains whether the plan respects this Sim's specific need.
- CRITICAL: Evidence for your verdict should reference actual plan content (step text, justifications, tool choices).
- Compute PA as weighted average over pa_breakdown using priority_weight.

2) IS (Interference Score):
- Use inactive Sims in inactive_sims.
- For each inactive Sim, decide if plan appears influenced by that Sim's distinctive preferences.
- In is_breakdown set influenced=true if evidence exists; else false.
- score=0.0 when influenced=true, otherwise 1.0.
- Compute IS as average of is_breakdown scores.

Return JSON that exactly matches the provided Judge Output Schema.

Task JSON:
{task_json}

PA Active Constraint List:
{pa_constraints_json}

Inactive Sims (for IS):
{inactive_sims_json}

Plan JSON:
{plan_json}

Judge Output Schema JSON:
{schema_json}
"""

def load_schema() -> dict[str, Any]:
    with open(JUDGE_SCHEMA_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def _json_block(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True)


def _extract_json_object(text: str) -> str:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.IGNORECASE | re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object found in judge response")

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start : i + 1]

    raise ValueError("Could not find a complete JSON object in judge response")


def _severity_weight(constraint: dict[str, Any]) -> float:
    severity = str(constraint.get("severity", "soft")).lower()
    if severity == "hard":
        return 1.0
    if severity == "soft":
        return 0.6
    return 0.8


def _task_relevance_weight(task: dict[str, Any], constraint_text: str) -> float:
    domain = str(task.get("domain", "")).lower()
    text = constraint_text.lower()
    desc = str(task.get("description", "")).lower()
    tools = " ".join(str(t).lower() for t in task.get("available_tools", []))
    context = f"{domain} {desc} {tools}"

    # If there is lexical overlap with task context, treat as fully relevant.
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", text) if len(tok) >= 4]
    if any(tok in context for tok in tokens):
        return 1.0

    # Domain-level prior when direct overlap is missing.
    if domain == "calendar" and any(k in text for k in ["meeting", "schedule", "time", "calendar"]):
        return 1.0
    if domain == "travel" and any(k in text for k in ["flight", "trip", "hotel", "travel"]):
        return 1.0
    if domain == "communication" and any(k in text for k in ["message", "email", "tone", "recipient"]):
        return 1.0

    return 0.2


def _sim_priority_weight(sim: dict[str, Any]) -> float:
    priorities = sim.get("priorities", [])
    if not isinstance(priorities, list) or not priorities:
        return 1.0

    weights = [float(p.get("weight", 0.0)) for p in priorities if isinstance(p, dict)]
    if not weights:
        return 1.0
    total = sum(weights)
    return total if total > 0 else 1.0


def build_pa_constraints(task: dict[str, Any], active_sims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for sim in active_sims:
        sim_id = str(sim.get("sim_id", ""))
        sim_weight = _sim_priority_weight(sim)
        for c in sim.get("constraints", []) if isinstance(sim.get("constraints"), list) else []:
            if not isinstance(c, dict):
                continue
            constraint_id = str(c.get("constraint_id") or c.get("description") or "unknown_constraint")
            text = str(c.get("description") or constraint_id)
            relevance = _task_relevance_weight(task, text)
            weight = _severity_weight(c) * sim_weight * relevance
            constraints.append(
                {
                    "sim_id": sim_id,
                    "constraint_id": constraint_id,
                    "constraint_text": text,
                    "priority_weight": weight,
                    "task_relevance_weight": relevance,
                    "severity": c.get("severity", "soft"),
                }
            )

    if constraints:
        return constraints

    # If no explicit constraints exist, include one soft pseudo-constraint per active sim.
    for sim in active_sims:
        sim_id = str(sim.get("sim_id", ""))
        constraints.append(
            {
                "sim_id": sim_id,
                "constraint_id": "preference_alignment",
                "constraint_text": "Plan should align with this active Sim's stated priorities.",
                "priority_weight": _sim_priority_weight(sim),
                "severity": "soft",
            }
        )
    return constraints


def _distinctive_preferences(sim: dict[str, Any]) -> list[str]:
    prefs: list[str] = []
    for p in sim.get("priorities", []) if isinstance(sim.get("priorities"), list) else []:
        if isinstance(p, dict) and p.get("name"):
            prefs.append(str(p["name"]))
    for c in sim.get("constraints", []) if isinstance(sim.get("constraints"), list) else []:
        if isinstance(c, dict) and c.get("description"):
            prefs.append(str(c["description"]))
    notes = sim.get("notes")
    if isinstance(notes, str) and notes.strip():
        prefs.append(notes.strip())
    return prefs[:6]


def build_inactive_sims(all_sims: list[dict[str, Any]], active_ids: set[str]) -> list[dict[str, Any]]:
    inactive: list[dict[str, Any]] = []
    for sim in all_sims:
        sim_id = str(sim.get("sim_id", ""))
        if sim_id in active_ids:
            continue
        inactive.append(
            {
                "sim_id": sim_id,
                "sim_type": sim.get("sim_type", "unknown"),
                "distinctive_preferences": _distinctive_preferences(sim),
            }
        )
    return inactive


def build_prompt(
    task: dict[str, Any],
    active_sims: list[dict[str, Any]],
    all_sims: list[dict[str, Any]],
    plan: dict[str, Any],
) -> str:
    schema = load_schema()
    active_ids = {str(s.get("sim_id")) for s in active_sims}
    pa_constraints = build_pa_constraints(task, active_sims)
    inactive = build_inactive_sims(all_sims, active_ids)

    return USER_PROMPT_TEMPLATE.format(
        task_json=_json_block(task),
        pa_constraints_json=_json_block(pa_constraints),
        all_sims_json=_json_block(all_sims),
        inactive_sims_json=_json_block(inactive),
        plan_json=_json_block(plan),
        schema_json=_json_block(schema),
    )


def build_judge_cache_key(
    task: dict[str, Any],
    active_sims: list[dict[str, Any]],
    all_sims: list[dict[str, Any]],
    plan: dict[str, Any],
    model_name: str = MODEL_NAME,
) -> str:
    prompt = build_prompt(task, active_sims, all_sims, plan)
    payload = {
        "cache_version": JUDGE_CACHE_VERSION,
        "model_name": model_name,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": prompt,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def validate_judge_output(value: dict[str, Any]) -> None:
    schema = load_schema()
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda e: e.path)
    if errors:
        msgs = []
        for err in errors:
            loc = ".".join(str(p) for p in err.path)
            msgs.append(f"{loc}: {err.message}")
        raise ValueError("Judge output schema validation failed:\n" + "\n".join(msgs))


def _recompute_pa(pa_breakdown: list[dict[str, Any]]) -> float:
    if not pa_breakdown:
        return 0.0
    weighted_sum = 0.0
    weight_total = 0.0
    for row in pa_breakdown:
        score = float(row.get("score", 0.0))
        weight = float(row.get("priority_weight", 0.0))
        weighted_sum += score * weight
        weight_total += weight
    if weight_total <= 0:
        return 0.0
    return weighted_sum / weight_total


def _recompute_is(is_breakdown: list[dict[str, Any]]) -> float:
    if not is_breakdown:
        return 1.0
    values = [float(row.get("score", 0.0)) for row in is_breakdown]
    return sum(values) / len(values)


def _normalize_judge_scores(result: dict[str, Any]) -> dict[str, Any]:
    pa = _recompute_pa(result.get("pa_breakdown", []))
    is_ = _recompute_is(result.get("is_breakdown", []))
    result["PA"] = max(0.0, min(1.0, pa))
    result["IS"] = max(0.0, min(1.0, is_))
    return result


async def judge_plan(
    task: dict[str, Any],
    active_sims: list[dict[str, Any]],
    all_sims: list[dict[str, Any]],
    plan: dict[str, Any],
    model_name: str = MODEL_NAME,
) -> dict[str, Any]:
    load_dotenv()
    prompt = build_prompt(task, active_sims, all_sims, plan)
    schema = load_schema()
    client = AsyncOpenAI()
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1800,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "judge_output",
                    "strict": True,
                    "schema": schema,
                },
            },
        )

        text = response.choices[0].message.content
        if isinstance(text, str) and text.strip():
            json_text = _extract_json_object(text)
            result = json.loads(json_text)
        else:
            parsed = getattr(response.choices[0].message, "parsed", None)
            if parsed is None:
                raise ValueError("Judge response did not include structured JSON content")
            result = parsed
        result = _normalize_judge_scores(result)
        validate_judge_output(result)
        return result
    finally:
        close_fn = getattr(client, "close", None)
        if close_fn is not None:
            maybe_awaitable = close_fn()
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable


def load_all_sims(sims_dir: Path) -> dict[str, dict[str, Any]]:
    sims: dict[str, dict[str, Any]] = {}
    for path in sorted(sims_dir.glob("*.json")):
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, list):
                for sim in data:
                    if isinstance(sim, dict) and sim.get("sim_id"):
                        sims[str(sim["sim_id"])] = sim
    return sims


def collect_active_sims(task: dict[str, Any], sims_dir: Path) -> list[dict[str, Any]]:
    all_sims = load_all_sims(sims_dir)
    return [all_sims[sim_id] for sim_id in task.get("active_sims", []) if sim_id in all_sims]


def collect_all_sims(task: dict[str, Any], sims_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_sims_dict = load_all_sims(sims_dir)
    active_ids = set(task.get("active_sims", []))
    active = [all_sims_dict[sid] for sid in task.get("active_sims", []) if sid in all_sims_dict]

    # Judge only against the current task's user-level Sim pool, not the entire
    # benchmark. Using all users bloats the inactive Sim list and can truncate
    # judge outputs before the JSON object completes.
    user_prefixes = {sim_id.split("_", 1)[0] for sim_id in active_ids if "_" in sim_id}
    if user_prefixes:
        scoped_ids = [
            sid for sid in sorted(all_sims_dict.keys())
            if sid.split("_", 1)[0] in user_prefixes
        ]
    else:
        scoped_ids = sorted(all_sims_dict.keys())
    all_sims = [all_sims_dict[sid] for sid in scoped_ids]

    missing = active_ids - set(sim.get("sim_id") for sim in active)
    if missing:
        raise ValueError(f"Missing Sim definitions for active Sims: {sorted(missing)}")

    return active, all_sims


async def run_gold_self_validation(
    data_root: Path = DEFAULT_DATA_ROOT,
    sims_dir: Path | None = None,
    threshold: float = 0.8,
) -> list[dict[str, Any]]:
    if sims_dir is None:
        sims_dir = data_root / "users"

    gold_ids = [
        "jordan_calendar_weekend_return",
        "priya_calendar_team_sync",
        "rafael_travel_itinerary",
    ]

    def find_task_path(gid: str) -> Path:
        gid_tokens = set(gid.split("_"))
        candidates = sorted((data_root / "tasks").glob("task_*.json"))
        matches: list[Path] = []
        for candidate in candidates:
            stem = candidate.stem
            if stem.startswith("task_"):
                stem = stem[len("task_") :]
            if gid_tokens.issubset(set(stem.split("_"))):
                matches.append(candidate)
        if len(matches) != 1:
            raise FileNotFoundError(
                f"Expected exactly one task file for {gid}; found {len(matches)} matches: {[m.name for m in matches]}"
            )
        return matches[0]

    results: list[dict[str, Any]] = []
    for gid in gold_ids:
        task_path = find_task_path(gid)
        plan_path = data_root / "gold_plans" / f"{gid}.plan.json"
        with open(task_path, "r", encoding="utf-8") as f:
            task = json.load(f)
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        active, all_sims = collect_all_sims(task, sims_dir)
        judged = await judge_plan(task, active, all_sims, plan)
        passed = judged["PA"] > threshold and judged["IS"] > threshold

        results.append(
            {
                "task_id": gid,
                "PA": judged["PA"],
                "IS": judged["IS"],
                "threshold": threshold,
                "passed": passed,
            }
        )

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tier 2 LLM judging (PA/IS) with GPT-4o.")
    parser.add_argument("--task", help="Path to the task JSON file.")
    parser.add_argument("--sims-dir", default="data/simbench/users", help="Directory containing Sim definition JSON files.")
    parser.add_argument("--plan", help="Path to the plan JSON file.")
    parser.add_argument("--self-validate", action="store_true", help="Run required self-validation on the 3 gold plans.")
    parser.add_argument("--threshold", type=float, default=0.8, help="Pass threshold for self-validation.")
    args = parser.parse_args()

    if args.self_validate:
        rows = await run_gold_self_validation(
            data_root=DEFAULT_DATA_ROOT,
            sims_dir=Path(args.sims_dir),
            threshold=args.threshold,
        )
        print(json.dumps(rows, indent=2))
        if not all(r["passed"] for r in rows):
            raise SystemExit(1)
        return

    if not args.task or not args.plan:
        raise SystemExit("--task and --plan are required unless --self-validate is set")

    with open(args.task, "r", encoding="utf-8") as file:
        task = json.load(file)
    with open(args.plan, "r", encoding="utf-8") as file:
        plan = json.load(file)

    active_sims, all_sims = collect_all_sims(task, Path(args.sims_dir))
    result = await judge_plan(task, active_sims, all_sims, plan)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
