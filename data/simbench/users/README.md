**SimBench Canonical Users**

This directory contains the **canonical user profiles** used throughout **SimBench**, the benchmark for evaluating **preference****conditioned agentic planning** via structured Sims.

Each user is represented as a **set of Sims** (context facets), not as a monolithic persona. A Sim captures a coherent, typed slice of user preferences (e.g., work, health, family), with explicit priorities and constraints. Tasks activate **one or more Sims**, and *the correct plan depends on which Sim(s) are active*.

These users are **reused across many tasks** to ensure consistency, comparability, and controlled variation.

**Design Principles**

The users in this directory are intentionally designed to satisfy the following properties:

- **Multi****context by construction**
Every user has at least two Sims, enabling conflicts by design.

- **Reusable across domains**
The same user can appear in travel, calendar, communication, and research tasks.

- **Conflict****rich but realistic**
Conflicts are defensible and interpretable (e.g., cost vs. health, work vs. family), not pathological.

- **Evaluation****friendly**
Constraints are written so that preference adherence and violations can be judged from a plan alone.

- **Synthetic but believable**
These are not real people, but reviewers should immediately recognize the scenarios.

**Canonical Users Overview**

| **User** | **Core Theme** | **Key Conflict Types** |
| --- | --- | --- |
| **Jordan Chen** | Multicontext professional | Priority, constraint, temporal, communication |
| **Alexa Morgan** | Startup operator | Temporal, health vs. speed |
| **Miguel Alvarez** | Budgetconstrained graduate student | Hard financial constraints |
| **Priya Natarajan** | Global manager | Timezone, fairness, family constraints |
| **Samir Patel** | Privacysensitive researcher | Privacy vs. convenience |
| **Emily Zhao** | Communicationfocused professional | Tone / communication conflicts |
| **Noah Williams** | Remote worker with logistics friction | Reliability and planning constraints |
| **Rafael Silva** | Experiencefirst traveler | Enjoyment vs. budget tradeoffs |

**File Structure and Format**

- Each file corresponds to **one user**.

- Files contain a **JSON array of Sims**, where each Sim conforms to:

																	- schemas/sim.schema.json

Example:

																user_01_jordan_chen.json

																├── jordan_work

																├── jordan_health

																├── jordan_family

																└── jordan_hobby

Each Sim is an independent unit with:

- its own priorities,

- its own constraints,

- its own communication style.

There is **no global “user preference blob.”**
All personalization happens via the selection and arbitration of Sims.

**How These Users Are Used in Experiments**

- Tasks reference users indirectly via their **Sim IDs**.

- A task specifies which Sims are **active** and their **priority order**.

- The agent must:

- Condition planning on the active Sim(s)

- Resolve conflicts correctly

- Avoid leakage from inactive Sims

The *same task description* may have multiple correct plans depending on which Sim is active.

**Adding or Modifying Users**

When extending this set:

✅ **Allowed**

- Adding new Sims to an existing user

- Adding new users following the same structure

- Refining constraint wording for clarity

🚫 **Not allowed (without versioning)**

- Changing Sim IDs (breaks task references)

- Removing constraints that existing gold plans depend on

- Collapsing multiple Sims into one

If a change would invalidate previously scored results, treat it as a **new benchmark version**.


**Notes**

- All users are **synthetic**.

- Names and scenarios are fictional.

- No real personal data is used.