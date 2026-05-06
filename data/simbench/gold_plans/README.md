# SimBench Gold Plans

This directory contains **gold‑standard plans** for selected SimBench tasks. Each gold plan represents the **reference correct behavior** for a task under a specific set of active Sims.

Gold plans are used to compute evaluation metrics such as:
- Plan Correctness (PC)
- Preference Adherence (PA)
- Interference Score (IS)
- Conflict Resolution Accuracy (CRA)

They are **authoritative** with respect to SimBench evaluation.

---

## What Is a Gold Plan?

A gold plan is a **fully specified, structured plan** that:

- Conforms to `schemas/plan.schema.json`
- Explicitly resolves all Sim conflicts
- Satisfies all hard constraints
- Optimizes soft priorities where possible
- Makes assumptions explicit

Gold plans are **not prompts**, **not model outputs**, and **not text explanations**. They are executable evaluation references.

---

## Scope of Gold Plans

Only a subset of SimBench tasks require gold plans. These are typically:

- High‑conflict tasks
- Tasks involving arbitration between multiple Sims
- Tasks where multiple plausible plans exist but only some are preference‑correct

This directory currently includes gold plans for the **hardest tasks**, where structured Sim reasoning matters most.

---

## File Naming Convention

Each gold plan is stored as a single JSON file:
<task_id>.plan.json

Example:
jordan_calendar_weekend_return.plan.json


Each gold plan corresponds to exactly **one task ID**.

---

## Authoring Principles

When writing or updating gold plans:

✅ **Required**
- Every plan step must be explicit
- Conflict resolution must be stated clearly
- Assumptions must be listed if information is missing

🚫 **Avoid**
- Implicit reasoning
- Relying on free‑text justification for correctness
- Optimizing for stylistic preferences over stated constraints

If a plan cannot be scored deterministically from its structure, it is not a valid gold plan.

---

## Versioning and Stability

Gold plans are tightly coupled to:
- task definitions
- Sim definitions
- evaluation metrics

Any change that alters expected behavior (e.g., changing a constraint from soft to hard) should be treated as a **breaking change** and requires updating the corresponding gold plan.

---

## Relation to the Paper

Gold plans operationalize the paper’s core evaluation claim:

> Preference‑conditioned agent behavior can be evaluated by comparing structured plans against explicit, Sim‑aware reference decisions.

They enable **fine‑grained analysis** of where and how agent outputs deviate from user‑consistent behavior.

---

## Notes

- All scenarios are synthetic.
- Gold plans represent *one defensible correct plan*, not the only possible plan.
- They are designed for research evaluation, not deployment.