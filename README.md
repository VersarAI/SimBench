# SimBench

**SimBench** is a benchmark for evaluating *preference-conditioned agentic planning* — the ability of an AI agent to produce different, correct plans for the same task depending on which user's preferences and constraints are active.

The core idea: instead of representing a user as a flat profile or a bag of retrieved facts, SimBench represents users as a set of **Sims** — structured, typed context facets (e.g. `jordan_work`, `jordan_health`, `jordan_family`). A task activates one or more Sims in priority order, and the correct plan depends on which Sims are active and how their conflicts are resolved.

---

## What's in this repo

```
data/simbench/
  tasks/          47 task instances across 4 domains
  users/          9 canonical user profiles (as Sim arrays)
  gold_plans/     3 reference plans for the hardest multi-Sim tasks
  metadata/       sims.json — index of all Sim definitions

schemas/
  task.schema.json        Task instance format
  sim.schema.json         Sim (context facet) format
  plan.schema.json        Agent plan format
  tools.schema.json       Abstract tool definitions by domain
  eval.schema.json        Evaluation output format

evaluation/
  metrics.py              Tier 1 deterministic metrics (PC, CRA)
  llm_judge.py            Tier 2 LLM judge (PA, IS)
  score_run.py            Combined scorer
  parser.py               Plan parser and repair
  sanity_check.py         Sanity checks against gold plans
  validate_judge.py       Judge output validator
```

---

## Task format

Each task is a JSON file specifying which Sims are active, what tools are available, and what conflict types are present.

```json
{
  "task_id": "jordan_travel_sf_conference",
  "domain": "travel",
  "description": "Plan travel and lodging for Jordan Chen to attend a three-day conference in San Francisco next week.",
  "active_sims": ["jordan_work", "jordan_health"],
  "available_tools": ["flight_search", "hotel_search", "itinerary_builder"],
  "conflict_types": ["priority_conflict", "constraint_conflict"],
  "difficulty": "medium"
}
```

Fields:
- `active_sims` — ordered list of Sim IDs; earlier Sims have higher priority
- `available_tools` — abstract tool names the agent may plan to use (no execution required)
- `conflict_types` — declared conflict categories, used for stratified analysis
- `difficulty` — `low`, `medium`, or `high`

### Dataset statistics

| | |
|---|---|
| Total tasks | 47 |
| Domains | calendar (17), research (11), travel (10), communication (9) |
| Difficulty | medium (25), high (15), hard (3), low (4) |
| Canonical users | 9 |
| Gold plans | 3 |

---

## Sim format

Each user is represented as a JSON array of Sims. Each Sim covers one context facet (work, health, family, hobby, etc.).

```json
{
  "sim_id": "jordan_health",
  "sim_type": "health",
  "priorities": [
    { "name": "sleep_quality", "weight": 0.6 },
    { "name": "exercise_access", "weight": 0.4 }
  ],
  "constraints": [
    {
      "constraint_id": "no_red_eye",
      "description": "Avoid red-eye flights.",
      "severity": "hard"
    }
  ],
  "communication_style": "brief and practical",
  "notes": "Training for a marathon."
}
```

**Arbitration rule:** when active Sims conflict, earlier Sims in `active_sims` take priority for soft constraints; hard constraints always override soft ones regardless of Sim order.

---

## Plan format

An agent response must be a JSON object conforming to `schemas/plan.schema.json`:

```json
{
  "plan_id": "my_plan_001",
  "steps": [
    {
      "step_id": "step_1",
      "tool": "flight_search",
      "parameters": { "items": [
        { "key": "origin", "value": "SEA" },
        { "key": "destination", "value": "SFO" },
        { "key": "class", "value": "economy" }
      ]},
      "justification": "Economy class stays within corporate expense policy."
    }
  ],
  "assumptions": ["Conference hotel not pre-booked."],
  "conflict_resolution": {
    "strategy": "weighted",
    "rationale": "jordan_work expense constraint (hard) takes precedence over jordan_health airline preference (soft)."
  }
}
```

---

## Evaluation metrics

SimBench uses two tiers of metrics:

**Tier 1 — deterministic (no LLM required)**
- **PC** (Plan Correctness): fraction of gold plan steps matched by tool name and required parameter keys
- **CRA** (Conflict Resolution Accuracy): whether the plan's declared conflict strategy matches the gold

**Tier 2 — LLM judge**
- **PA** (Preference Adherence): how well the plan satisfies the active Sims' priorities and constraints
- **IS** (Interference Score): whether inactive Sim preferences inappropriately leaked into the plan

The Tier 2 judge uses OpenAI's API and requires an `OPENAI_API_KEY`.

---

## Quickstart

```bash
pip install -r requirements.txt
```

**Score a single plan against a task:**

```python
import json
from evaluation.metrics import score_tier1

task = json.load(open("data/simbench/tasks/task_travel_jordan_sf_conference.json"))
gold = json.load(open("data/simbench/gold_plans/rafael_travel_itinerary.plan.json"))
plan = json.load(open("my_agent_output.json"))

scores = score_tier1(task, plan, gold)
print(scores)  # {"PC": 0.67, "CRA": 1.0}
```

**Run the LLM judge (Tier 2):**

```bash
export OPENAI_API_KEY=sk-...
python -m evaluation.llm_judge \
  --task data/simbench/tasks/task_travel_jordan_sf_conference.json \
  --plan my_agent_output.json \
  --sims-dir data/simbench/users
```

**Validate your plans against the schema:**

```bash
python -m evaluation.sanity_check
```

---

## Canonical users

| User | Core theme | Key conflict types |
|---|---|---|
| Jordan Chen | Multi-context professional | Priority, constraint, temporal |
| Alexa Morgan | Startup operator | Temporal, health vs. speed |
| Miguel Alvarez | Budget-constrained graduate student | Hard financial constraints |
| Priya Natarajan | Global manager | Timezone, fairness, family |
| Samir Patel | Privacy-sensitive researcher | Privacy vs. convenience |
| Emily Zhao | Communication-focused professional | Tone and style |
| Noah Williams | Remote worker | Reliability and logistics |
| Rafael Silva | Experience-first traveler | Enjoyment vs. budget |
| Diana Osei | (additional user) | Mixed |

All users and scenarios are synthetic. No real personal data is used.

---

## License

MIT — see [LICENSE](LICENSE).
