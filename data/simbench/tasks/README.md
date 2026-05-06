# SimBench Tasks

This directory contains **SimBench task instances** used to evaluate **preference‑conditioned agentic planning** under structured, multi‑context user representations (Sims).

Each task is designed so that the *correct plan depends on which Sim(s) are active*. The same high‑level task description may yield **different correct tool-use plans** depending on user context, priorities, and constraints.

---

## What Makes a SimBench Task

A SimBench task is not just a prompt. Each task explicitly defines:

- **Which Sims are active** (and in what priority order)
- **Which tools are available** (abstractly)
- **What types of conflicts are present**
- **How difficult the task is to resolve correctly**

All tasks in this directory conform to:
schemas/task.schema.json


---

## Task Design Principles

The tasks in this directory follow five core principles:

1. **Preference sensitivity**
   - Tasks are constructed so that flat profiles or no-profile baselines are insufficient.

2. **Conflict by design**
   - Most tasks include at least one explicit conflict:
     - priority conflicts
     - hard vs. soft constraint conflicts
     - temporal conflicts
     - communication-style conflicts

3. **Cross-domain reuse**
   - The same canonical users appear across:
     - travel
     - calendar/scheduling
     - communication
     - information research

4. **Tool-abstract planning**
   - Tools are symbolic (e.g., `flight_search`, `calendar_view`).
   - Evaluation focuses on *planning decisions*, not tool execution.

5. **Evaluation tractability**
   - Tasks are written so that plan correctness and preference adherence can be judged from structured outputs alone.

---

## File Structure

Each task is stored as a single JSON file:
task_<domain><em><user></user></em><scenario>.json</scenario></domain>

Example:
task_travel_jordan_sf_conference.json


Each task file specifies:
- `task_id`
- `domain`
- `description`
- `active_sims`
- `available_tools`
- `conflict_types`
- `difficulty`

---

## Canonical Task Set (Initial)

The initial task set includes **8–10 tasks**, covering all domains and users:

| User | Domain(s) | Key Conflict Types |
|----|----|----|
| Jordan Chen | Travel, Calendar | Priority, constraint, temporal |
| Alexa Morgan | Calendar | Temporal, health vs. speed |
| Miguel Alvarez | Travel | Hard budget constraints |
| Priya Natarajan | Calendar | Time-zone, fairness, family |
| Samir Patel | Research | Privacy vs. convenience |
| Emily Zhao | Communication | Tone and style |
| Noah Williams | Research | Logistics and reliability |
| Rafael Silva | Travel | Experience vs. budget |

This scale is **intentional**: a small number of users with high task reuse yields clearer attribution of effects than many one-off personas.

---

## Relationship to Gold Plans

Each task in this directory is paired with a **gold-standard plan** stored under:
data/simbench/gold_plans/


Gold plans:
- conform to `schemas/plan.schema.json`
- explicitly resolve Sim conflicts
- serve as the reference for metric computation

Tasks and gold plans are versioned together; modifying a task may invalidate prior gold plans.

---

## Adding New Tasks

✅ **Recommended**
- Reuse existing users and Sims
- Introduce new conflict combinations
- Vary locations, dates, or tool availability

🚫 **Avoid**
- Tasks whose correct behavior does not depend on user preferences
- Tasks that collapse multiple decisions into a single opaque step
- Implicit conflicts that are not declared in `conflict_types`

If a task does not require Sim-aware arbitration, it is not suitable for SimBench.

---


## Notes

- All tasks are synthetic.
- Names, scenarios, and constraints are fictional.
- Tasks are designed for research evaluation, not deployment.