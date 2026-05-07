---
id: token-budgets-and-cost-gates
title: Per-project token budgets & cost gates
type: design
status: active
owner: ro
created: '2026-04-18'
updated: '2026-05-06'
last_verified_at: '2026-05-06'
summary: Per-project token budgets and cost-gate enforcement.
verified_by: coder@vibedevx.com
implements_specs: []
decided_by: []
related_designs:
- observability-and-cost-tracking
- worker-communication
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-admin
parent: pipeline-operations
---
# Per-project token budgets & cost gates

## Context

Cost flows today look like: worker runs → response envelope carries
`input_tokens` + `output_tokens` → dispatcher writes them to
`tasks` → `/metrics` rolls up. There's no enforcement in that path.
This design inserts a pre-dispatch gate + post-completion rollup,
both keyed on a new `project_budget_period` table that aggregates
the per-task spend into a per-month-per-project bucket.

The enforcement is deliberately simple: a lookup of
`tokens_used < hard_cap` before dispatch, and a same-table rollup
write after completion. No distributed counters, no token pools —
one row per project per month, updated transactionally.

## Goals / non-goals

**Goals**
- Per-project soft and hard caps, backed by a monthly rollup
  table with an audit trail.
- Pre-dispatch gate that refuses to dispatch over hard cap.
- Soft-cap downshift that piggybacks on 0030's tier router.
- Admin UI for setting caps, viewing current usage, and
  granting overrides.
- Slack alerts dedup'd per (project, threshold, month).

**Non-goals**
- Distributed counters. One-row-per-month is the coordinator.
- Dollar-denominated display (that's a front-end concern that
  can read the token-per-dollar ratio from Anthropic's pricing
  table).
- Per-task reservations or quota pre-allocation.
- Invoice-cycle alignment (calendar month is the period).

## Design

```mermaid
flowchart TB
  subgraph core [coder-core]
    dispatch[dispatcher pre-gate]
    budget_check[check_budget]
    period[(project_budget_period)]
    tasks[(tasks)]
    projects[(projects)]
    hook[task-completion hook]
    cron[monthly reset cron]
    slack[Slack webhook]
    api[/budget API]
    patch["PATCH /projects/:id"]
  end

  subgraph admin [coder-admin]
    list[projects list \n budget column]
    detail[project detail\n budget card]
    override[override modal]
  end

  dispatch --> budget_check
  budget_check -->|read used + caps| period
  budget_check -->|read caps| projects
  budget_check -->|over hard| tasks
  budget_check -->|ok| worker[role worker]
  worker --> hook
  hook -->|INCR tokens_used| period
  hook -->|soft breach?| slack
  hook -->|hard breach?| slack
  hook -->|soft → downshift flag| projects
  cron -->|month rollover| period
  api --> period
  api --> projects
  patch --> projects
  list --> api
  detail --> api
  override --> tasks
```

### Parts

- **Migration: `projects.budget_soft_tokens`,
  `projects.budget_hard_tokens`** — both `BIGINT NULL`.
  NULL = fall back to fleet defaults (`budget_default_soft`,
  `budget_default_hard` in settings). Bulk-nullable is
  deliberate — lets us enable the system without
  retroactively classifying every project.
- **Migration: `projects.budget_downshift_active_until_month_end`**
  — `BOOLEAN NOT NULL DEFAULT FALSE`. Set by the task-
  completion hook on soft breach; cleared by the monthly
  reset cron.
- **Migration: `project_budget_period`** — one row per
  `(project_id, period_yyyymm)`. Columns:
  - `project_id TEXT NOT NULL REFERENCES projects(id)`
  - `period_yyyymm INT NOT NULL` (e.g. `202604`)
  - `tokens_used BIGINT NOT NULL DEFAULT 0`
  - `soft_breach_at TIMESTAMPTZ NULL`
  - `hard_breach_at TIMESTAMPTZ NULL`
  - `downshift_activated_at TIMESTAMPTZ NULL`
  - `last_slack_alert_at TIMESTAMPTZ NULL` (dedupe anchor)
  - `last_override_at TIMESTAMPTZ NULL`
  - `override_granted_by TEXT NULL`
  - `PRIMARY KEY (project_id, period_yyyymm)`
  - Index on `(period_yyyymm, project_id)` for month-wide
    rollups.
- **Migration: `tasks.budget_override_granted_at`** —
  `TIMESTAMPTZ NULL`. Per-task override: set by the admin
  panel's override affordance when an operator chooses to
  let a single blocked task through.
- **Migration: `tasks.failure_kind` enum add `"budget"`** —
  task classifier gains a new case; the dispatcher writes
  `failure_kind="budget"` + the offending cap in the
  `failure_detail` JSON when a dispatch is refused.
- **`coder_core.budget` module** — new:
  - `async def check_budget(project_id, task_id) -> BudgetDecision`
    — reads project caps + current-period usage; returns
    one of `allow`, `soft_warn`, `hard_block`. Called from
    the dispatcher pre-gate.
  - `async def record_usage(project_id, period, tokens_used)`
    — atomically increments the period row; returns the
    post-increment (used, soft, hard) triple so the
    completion hook can fire alerts without a re-read.
  - `async def reset_budget_period(now)` — monthly cron;
    no-op if current period row doesn't exist.
- **Dispatcher pre-gate** (`coder_core.workers.dispatcher`)
  calls `check_budget` for every task before the worker
  spawn. Decision:
  - `allow` → continue.
  - `soft_warn` → continue; flip
    `projects.budget_downshift_active_until_month_end = true`
    if not already; fire Slack alert (dedup'd).
  - `hard_block` → if `tasks.budget_override_granted_at`
    is set, continue; else set `tasks.status=budget_blocked`
    + `failure_kind="budget"` + fire Slack alert
    (dedup'd); do not dispatch.
- **Task-completion hook** (`coder_core.workers.pipeline_chain`
  or similar post-hook) — after a task completes, reads the
  `input_tokens + output_tokens` (plus 0029's
  `cache_creation_input_tokens` if present — those are a real
  spend; `cache_read_input_tokens` cost less but still
  counted; model-specific ratios live in a module constant
  and evolve with Anthropic pricing). Calls `record_usage()`.
  Checks the post-increment: if crossed soft or hard for the
  first time this month, fires Slack (`last_slack_alert_at`
  bumps for dedupe).
- **Monthly reset cron** — runs at 00:05 UTC on the 1st of
  each month. Creates the new-period row (lazily — any
  task in the new period also creates it on first write);
  clears `projects.budget_downshift_active_until_month_end`.
- **Budget API** — `GET /v1/projects/{id}/budget`. Returns:
  ```json
  {
    "period_yyyymm": 202604,
    "period_reset_at": "2026-05-01T00:00:00Z",
    "soft_cap": 2000000,
    "hard_cap": 3000000,
    "used": 1250000,
    "soft_breach_at": "2026-04-17T14:22:00Z",
    "hard_breach_at": null,
    "downshift_active": true
  }
  ```
  Project API key scopes access; admin JWT returns any
  project.
- **`PATCH /v1/projects/{id}`** — accepts
  `budget_soft_tokens` / `budget_hard_tokens`. Existing
  endpoint pattern; admin JWT or project owner via API key.
- **Admin: budget column + card** — Recharts progress bar,
  soft-breach amber, hard-breach red. Override modal on
  `budget_blocked` task detail sets
  `tasks.budget_override_granted_at` + re-dispatches.

### Data flow

**Normal task dispatch:**

1. Task lands in `PENDING`.
2. Dispatcher pulls it off the queue.
3. Calls `check_budget(project_id)`.
4. `allow` → dispatch as normal.
5. Worker completes; completion hook calls `record_usage()`.
6. Post-increment shows (used=1.3M, soft=2.0M, hard=3.0M)
   → no breach → done.

**Soft breach:**

1. Same dispatch path; task runs normally.
2. Completion hook: post-increment shows (used=2.1M, soft=2.0M).
3. Atomic test-and-set: `soft_breach_at IS NULL` →
   set it to now; flip
   `projects.budget_downshift_active_until_month_end`;
   fire Slack (`last_slack_alert_at` set).
4. Next task dispatched on the project: `check_budget`
   returns `allow` (still under hard); 0030's
   `_model_for_task` observes the downshift flag and
   forces `low_tier` on the task.

**Hard breach:**

1. Task pre-gate: `check_budget` returns `hard_block`.
2. Dispatcher sets `tasks.status=budget_blocked`,
   `failure_kind="budget"`, `failure_detail = {"cap_hit":
   "hard", "cap_value": 3000000, "used": 3010000}`.
3. Slack alert fires (dedup'd per month).
4. Admin panel shows the task in a new `budget_blocked`
   bucket; operator hits **Override**.
5. Override sets `tasks.budget_override_granted_at`,
   `project_budget_period.last_override_at`,
   `override_granted_by = <operator email>`.
6. Dispatcher re-pulls the task; pre-gate sees the
   override and dispatches.
7. Completion hook does NOT set
   `downshift_active_until_month_end` again — it's
   already set from the soft breach.

### Invariants

- **One rollup row is the only writable counter.** Every
  task-completion hook writes to exactly one
  `project_budget_period` row via an atomic
  `UPDATE ... RETURNING used_after`. Concurrent completions
  serialise on the row lock. No distributed counters.
- **Dispatch and rollup are separate transactions.** The
  pre-gate reads, makes a decision, and the completion
  hook writes. A race (two tasks dispatch at 2.99M, push
  to 3.05M) is acceptable — the next task after them will
  hard-block. We aren't trying to enforce "never cross
  the cap by a token"; we're trying to prevent runaway.
- **Override is per-task, not per-project-for-a-window.**
  Each `budget_blocked` task needs its own override; an
  operator can't flip a project to "unblocked for 24 h"
  and walk away. If that's needed, raise the hard cap
  temporarily via `PATCH /projects`.
- **Calendar month is the period.** UTC 00:00 on the 1st.
  No DST, no tenant-local calendars.
- **Fleet default is a floor, not a ceiling.** Per-project
  `budget_*_tokens` NULL → fleet default applies. A
  project that sets a non-NULL value fully overrides the
  fleet default in either direction.

## Open questions

- Should `cache_creation_input_tokens` count against budget
  at full rate or discounted? Anthropic bills cache writes
  at a premium but reads at a discount — our "tokens_used"
  wants to approximate billable spend, not literal bytes
  sent. Leaning: count cache-creation at 1.25× (matches
  Anthropic's billing multiplier), cache-read at 0.1×. Pin
  in design review.
- Where does the dispatcher pre-gate sit relative to
  0028's `DispatcherQueue`? Pre-gate runs *after* the
  queue emits a task (so a budget-blocked task doesn't
  wedge the queue, it just lands in `budget_blocked`
  status and the queue moves on).
- Retention on `project_budget_period` — keep forever or
  archive after 12 months? Forever for this first cut; the
  rollup is small (one row per project per month).

## Rollout

Three phases:

**Phase 1 — schema + rollup, no gate.** Migrations land;
completion hook starts writing to
`project_budget_period`. Pre-gate is deployed but in
dry-run mode: it logs the decision it would make without
enforcing. Admin panel shows the column. Flag
`budget_gates_enabled: bool = False`. 7-day shadow to
verify the rollup matches `/metrics`.

**Phase 2 — soft enforcement.** Flip flag. Soft breach
triggers downshift + Slack. Hard breach still dry-run
(logs the would-block, doesn't actually block). 7-day
soak to verify downshift works and Slack dedup holds.

**Phase 3 — hard enforcement.** Hard breach actually
blocks. Operators get the override flow. 48 h on a canary
project before fleet enable.

**Backout plan.** `budget_gates_enabled=False` → pre-gate
reverts to dry-run logging. Rollup keeps running (benign).
Expected backout: one config flip.

## Links

- Specs: [0031 — token budgets](../../product-specs/wip/0031-token-budgets.md),
  [observability](../../product-specs/active/observability.md),
  [task-orchestration](../../product-specs/active/task-orchestration.md),
  [admin-panel](../../product-specs/active/admin-panel.md).
- ADRs: none yet.
- Services: coder-core (migrations, budget module, pre-gate,
  completion hook, cron, API), coder-admin (column, card,
  override modal).
- Related designs: [0029 — prompt caching](./0029-prompt-caching.md)
  (cache-creation tokens feed into the spend counter),
  [0030 — tier routing](./0030-model-tier-routing.md)
  (downshift signal),
  [observability-and-cost-tracking](../active/observability-and-cost-tracking.md),
  [worker-communication](../active/worker-communication.md)
  (dispatcher pre-gate insertion point).
