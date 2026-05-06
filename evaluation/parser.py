# evaluation/parser.py

import json
import re
from jsonschema import Draft7Validator
from pathlib import Path


class PlanValidationError(Exception):
    pass


def _enforce_non_empty_steps(plan: dict) -> None:
    """Hard guardrail independent of JSON schema file drift.

    Some runs may accidentally validate against an outdated schema that does not
    require `steps`. We reject such plans here to keep parse_success aligned with
    downstream scoring expectations.
    """
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list) or len(steps) < 1:
        raise PlanValidationError("Hard validation failed: plan must contain a non-empty 'steps' array.")


def load_schema(schema_path: Path) -> dict:
    with open(schema_path, "r") as f:
        return json.load(f)


def load_and_validate_plan(
    plan_path: Path,
    plan_schema_path: Path,
) -> dict:
    """
    Load a plan JSON file and validate it against the Plan schema.
    Raises PlanValidationError on failure.
    """
    try:
        with open(plan_path, "r") as f:
            plan = json.load(f)
    except json.JSONDecodeError as e:
        raise PlanValidationError(f"Invalid JSON: {e}")

    schema = load_schema(plan_schema_path)
    validator = Draft7Validator(schema)

    errors = sorted(validator.iter_errors(plan), key=lambda e: e.path)
    if errors:
        messages = []
        for err in errors:
            loc = ".".join(map(str, err.path))
            messages.append(f"{loc}: {err.message}")
        raise PlanValidationError(
            "Schema validation failed:\n" + "\n".join(messages)
        )

    _enforce_non_empty_steps(plan)

    return plan


def _strip_code_fences(text: str) -> str:
    candidate = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return candidate


def _extract_first_complete_json_object(text: str) -> str:
    """Extract the first complete JSON object by brace matching.

    Handles quoted strings and escaped characters while scanning.
    If the model response is truncated but otherwise structurally consistent,
    the function repairs the tail by closing any remaining open containers.
    """
    start = text.find("{")
    if start == -1:
        raise PlanValidationError("No JSON object start ('{') found in response.")

    stack: list[str] = []
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]

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

        if ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
            if not stack:
                return text[start:i + 1]
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()

    candidate = text[start:].rstrip()
    if not candidate:
        raise PlanValidationError("No complete JSON object found (empty candidate).")

    if in_string:
        candidate += '"'

    while candidate and candidate[-1] in {",", ":"}:
        candidate = candidate[:-1].rstrip()

    closers = []
    for opener in reversed(stack):
        closers.append("}" if opener == "{" else "]")

    repaired = candidate + "".join(closers)
    return repaired


def _remove_trailing_commas(text: str) -> str:
    # Remove trailing commas before object/array closure.
    return re.sub(r",\s*([}\]])", r"\1", text)


def _scalarize(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalize_step_shape(plan: dict) -> None:
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return

    normalized_steps = []
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue

        if not step.get("tool"):
            # Truncated final fragments are common in long model outputs.
            continue

        step["step_id"] = str(step.get("step_id", idx))
        if "justification" not in step:
            step["justification"] = None

        params = step.get("parameters")
        if isinstance(params, dict):
            if isinstance(params.get("items"), list):
                normalized_items = []
                for item in params["items"]:
                    if not isinstance(item, dict) or "key" not in item:
                        continue
                    normalized_items.append(
                        {
                            "key": str(item.get("key")),
                            "value": _scalarize(item.get("value")),
                        }
                    )
                step["parameters"] = {"items": normalized_items}
            else:
                step["parameters"] = {
                    "items": [
                        {"key": str(key), "value": _scalarize(value)}
                        for key, value in params.items()
                    ]
                }
        elif params is None:
            step["parameters"] = {"items": []}
        else:
            step["parameters"] = {"items": [{"key": "value", "value": _scalarize(params)}]}

        normalized_steps.append(step)

    plan["steps"] = normalized_steps


def _normalize_conflict_resolution(plan: dict) -> None:
    value = plan.get("conflict_resolution")

    if isinstance(value, dict):
        strategy = value.get("strategy") or "weighted"
        rationale = value.get("rationale") or value.get("resolution") or value.get("conflict")
        plan["conflict_resolution"] = {
            "strategy": str(strategy),
            "rationale": str(rationale or "Conflict handling was inferred from the model response."),
        }
        return

    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                fragment = "; ".join(
                    str(item.get(key)).strip()
                    for key in ("conflict", "resolution", "rationale")
                    if item.get(key)
                )
                if fragment:
                    parts.append(fragment)
            elif item is not None:
                parts.append(str(item).strip())
        plan["conflict_resolution"] = {
            "strategy": "weighted" if parts else "none",
            "rationale": " | ".join(parts) or "No explicit conflict details were provided.",
        }
        return

    if isinstance(value, str):
        lowered = value.strip().lower()
        plan["conflict_resolution"] = {
            "strategy": "none" if lowered in {"none", "no conflict", "no conflicts"} else "weighted",
            "rationale": value.strip() or "No explicit conflict resolution provided.",
        }
        return

    plan["conflict_resolution"] = {
        "strategy": "none",
        "rationale": "No explicit conflict resolution provided.",
    }


def _repair_plan_shape(plan: dict) -> dict:
    if not isinstance(plan, dict):
        return plan

    if not plan.get("plan_id") and plan.get("name"):
        plan["plan_id"] = str(plan["name"])

    assumptions = plan.get("assumptions")
    if assumptions is None:
        plan["assumptions"] = []
    elif not isinstance(assumptions, list):
        plan["assumptions"] = [str(assumptions)]
    else:
        plan["assumptions"] = [str(_scalarize(item)) for item in assumptions]

    _normalize_step_shape(plan)
    _normalize_conflict_resolution(plan)
    return plan


def parse_response_plan(response_text: str, plan_schema: dict) -> dict:
    """Parse and validate a raw model response into a plan dict.

    Repair sequence:
    1) Strip markdown code fences.
    2) Extract first complete JSON object via brace matching.
    3) Remove trailing commas before } or ].
    4) json.loads on cleaned text.
    5) Validate against plan schema.
    """
    cleaned = _strip_code_fences(response_text)
    cleaned = _extract_first_complete_json_object(cleaned)
    cleaned = _remove_trailing_commas(cleaned)

    try:
        plan = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise PlanValidationError(f"Invalid JSON after repair: {e}")

    plan = _repair_plan_shape(plan)

    validator = Draft7Validator(plan_schema)
    errors = sorted(validator.iter_errors(plan), key=lambda e: e.path)
    if errors:
        messages = []
        for err in errors:
            loc = ".".join(map(str, err.path))
            messages.append(f"{loc}: {err.message}")
        raise PlanValidationError("Schema validation failed:\n" + "\n".join(messages))

    _enforce_non_empty_steps(plan)

    return plan