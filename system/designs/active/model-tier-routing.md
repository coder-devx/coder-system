---
id: model-tier-routing
title: Model tier routing
type: design
status: active
owner: ro
created: '2026-04-18'
updated: '2026-05-06'
last_verified_at: '2026-05-06'
verified_by: coder@vibedevx.com
implements_specs: []
decided_by: []
related_designs:
- worker-roles
- worker-communication
- observability-and-cost-tracking
- pm-worker
- architect-worker
- team-manager-worker
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-admin
- coder-system
parent: pipeline-operations
---
# Model tier routing

## Context

Every role worker's dispatcher calls `anthropic.messages.create()`
with a hard-coded `model="claude-…"` constant. The constant points
at the top tier. That's overpaid on any task whose historical
Reviewer approval rate is ≥95% on top tier — we've clearly already
cleared the quality bar, so a cheaper tier should land the same
output with a cost reduction proportional to the tier delta.

The shape of the fix: replace the constant with a lookup against a
policy table, keyed by `(role, task_kind)`. Policy is declarative
(a YAML file in `template/`), ships per-project via normal
template-adoption flow, overridable per-task for retries, and
shadow-soakable before enabling. Chains on 0029's infrastructure
(the response envelope already carries `model` and per-tier token
counts; we just need to record and roll them up by tier).

## Goals / non-goals

**Goals**
- One lookup function, one migration, one config file — no
  per-role special cases.
- Per-task override for escalation on retry.
- Per-project pin to top tier for projects that need quality
  guarantees over cost.
- Per-tier rollup on `/metrics` and the admin dashboard.
- Shadow soak path: capture `model_id` on every task whether
  or not routing is on, so the baseline is readable before
  the canary flip.

**Non-goals**
- Policy auto-learning. Policy is human-edited based on the
  per-tier approval-rate gauge.
- Cross-provider routing.
- Rewriting prompts per tier.
- Speculative execution (run Haiku, fall back to Sonnet).

## Design

```mermaid
flowchart TB
  subgraph core [coder-core]
    policy[model_tier_policy.yaml<br/>from template/]
    resolver[_model_for_task resolver]
    orch[orchestrator dispatch]
    worker[role worker]
    tasks[(tasks table)]
    metrics[/metrics API]
  end

  subgraph anthropic [Anthropic API]
    msgs[messages.create model=...]
  end

  subgraph admin [coder-admin]
    dash[/metrics dashboard<br/>per-tier card]
  end

  policy --> resolver
  orch -->|role, task_kind, override| resolver
  resolver -->|model_id| worker
  worker -->|model=model_id| msgs
  msgs -->|response.model = echoed| worker
  worker -->|write model_id| tasks
  tasks --> metrics
  metrics --> dash
```

### Parts

- **Template file: `template/model_tier_policy.yaml`** —
  ships per-project via the normal template-adoption
  path. Example shape:
  ```yaml
  defaults:
    top_tier: claude-opus-4-7
    mid_tier: claude-sonnet-4-6
    low_tier: claude-haiku-4-5-20251001
  routes:
    pm:
      draft: mid_tier
      accept: low_tier
    architect:
      design: top_tier
      ship_draft: mid_tier
      knowledge_audit: mid_tier
    team_manager:
      plan: mid_tier
      close_cycle: low_tier
    developer:
      task: top_tier  # dev work stays top until we've soaked enough data
    reviewer:
      review: mid_tier
      ship_attestation: mid_tier
  ```
  Validated at project-load time and by `scripts/validate.py`
  (every `(role, task_kind)` known to the code must have an
  entry or resolution falls back to top_tier with a warning).
- **Resolver: `coder_core.workers.routing._model_for_task`** —
  new module. Signature:
  ```python
  def _model_for_task(
      project_id: str,
      role: str,
      task_kind: str,
      override: str | None,
      *,
      settings: Settings,
      project: Project,
  ) -> str: ...
  ```
  Resolution order:
  1. If `override` is set: use it.
  2. If `project.pin_top_tier` is True: use `defaults.top_tier`.
  3. If `settings.tier_routing_enabled` is False: use
     `defaults.top_tier`.
  4. Look up `routes[role][task_kind]` → one of `low_tier |
     mid_tier | top_tier` → resolve via `defaults`.
  5. On miss: log a warning (`no_route_policy`), fall back to
     `defaults.top_tier`. Missing policy is a quality-safe
     default, not a hard failure.

  Called by every role worker's dispatch path exactly once per
  task. Result is persisted on `tasks.model_id` at dispatch
  time so the metrics rollup is a single-table scan.
- **Migration: `tasks.model_tier_override`** — nullable TEXT
  column. Written by the orchestrator's schema-retry path: if
  a task at tier T fails with `failure_kind="schema"`, the
  re-dispatch sets `model_tier_override = <next-tier-up>`.
  Preserves the audit trail — you can tell from the row
  whether the task ran on its policy tier or escalated.
- **Migration: `projects.pin_top_tier`** — `BOOLEAN NOT NULL
  DEFAULT FALSE`. Per-project opt-out lever described in the
  spec.
- **`tasks.model_id` already exists** (0027 wrote the response
  envelope's `model` field in the cost rollup). This spec
  flips `model_id` from "informational record" to "primary
  dispatch-time decision" — a rename of the column wasn't
  needed, just a semantic clarification in the design.
- **Settings flag** — `tier_routing_enabled: bool = False`.
  Gated on 0029 shipping (the baseline cost numbers are only
  meaningful once caching is in steady state).
- **Metrics API extension** — `/v1/projects/{id}/metrics?period=1d|7d|30d`
  gains:
  ```json
  {
    "by_tier": {
      "claude-opus-4-7": {
        "task_count": 1450, "approval_rate": 0.98,
        "avg_cost": 0.84, "avg_duration_s": 45.2
      },
      "claude-sonnet-4-6": { ... },
      "claude-haiku-4-5-20251001": { ... }
    }
  }
  ```
  Computed from the existing `tasks` rollup with a `GROUP BY
  model_id` — no new tables.
- **Admin `/metrics` card** — Recharts stacked bar: per-tier
  task volume + per-tier approval rate overlay. Lives next to
  0029's cache-hit card (same row).

### Data flow

**Task dispatch:**

1. Orchestrator resolves `(role, task_kind)` for the task
   (already known — task_kind is on the task row).
2. Calls `_model_for_task(...)` once; receives a concrete
   `model_id`.
3. Writes `tasks.model_id = model_id` on the row (this
   replaces the post-hoc write from the response envelope).
4. Worker dispatches with that `model_id`.
5. Anthropic response echoes `model = model_id` (sanity check:
   if echo ≠ requested, log `model_mismatch` and keep the
   requested value as the record of intent).
6. Task completes; metrics rollup aggregates by `model_id`.

**Schema-retry escalation:**

1. Task fails with `failure_kind="schema"` (existing 0025
   loop).
2. Retry dispatcher (existing) reads
   `tasks.model_id` from the failed row; resolves the
   next tier up (low → mid → top; top stays top).
3. Sets `model_tier_override = <next-tier>` on the new task
   row; dispatch resolves via override.
4. New task runs at escalated tier.

### Invariants

- **One row records one decision.** `tasks.model_id` is set
  at dispatch, not at response-parse time. Two rows mean two
  decisions — schema retries produce a new row, not a
  mutation of the old one.
- **Policy miss is safe.** Any missing `routes[role][task_kind]`
  entry resolves to `defaults.top_tier` — the existing
  behaviour. No task ever runs on a cheaper tier without an
  explicit policy entry.
- **Per-project opt-out wins over fleet enable.** A project
  with `pin_top_tier=True` never sees routing applied, even
  if the fleet flag is on.
- **Retries only ever escalate.** Schema retries can go low
  → mid → top; a top-tier retry stays on top. The retry
  override is one-shot: the second retry re-reads the policy
  (it won't keep escalating past top).

## Open questions

- Where does `task_kind` come from for role workers that
  dispatch multi-kind (e.g. Architect does `design`,
  `ship_draft`, `knowledge_audit`)? Today the dispatcher
  infers from the prompt prefix; this spec should pin it
  onto the task row explicitly so the resolver doesn't need
  to re-parse the prompt.
- Does the policy YAML live under `template/` (per-project)
  or is it a singleton shipped with coder-core? Leaning
  per-project, via template adoption — lets audit projects
  pin `pin_top_tier` without affecting others, and lets us
  A/B tier policies across projects with different risk
  tolerances.
- Interaction with 0029 cache: cache is keyed on model. A
  tier flap mid-pipeline invalidates the cache. Should the
  policy enforce "one tier per pipeline run for a given
  role" to keep cache hits high? Probably yes — but it's a
  design comment, not a new mechanism.

## Rollout

Four phases, same shape as 0029:

**Phase 1 — migration + baseline capture.** Add `model_id` as
dispatch-time column (carries existing semantics; no behavior
change). Add `model_tier_override` and `pin_top_tier` columns.
Metrics API exposes `by_tier` (reads 1-tier during shadow).
Flag stays False.

**Phase 2 — policy file + resolver wired.** Ship
`template/model_tier_policy.yaml` with every role+task_kind
mapped to top_tier (status-quo). Resolver lands; every worker's
dispatch goes through it. Still no behaviour change — every
lookup resolves to top_tier by policy, not by hard-code.

**Phase 3 — canary enable.** On one project, hand-edit its
`model_tier_policy.yaml` to demote the safest routes (TM
`close_cycle`, PM `accept`) from top_tier to mid_tier. Flip
`tier_routing_enabled=True` for that project only (via
`projects.tier_routing_override` or fleet flag, depending on
the opt-in mechanism — pin this in review). Watch the per-tier
approval-rate gauge for 7 days.

**Phase 4 — progressive fleet enable.** Demote more routes as
the per-tier data comes in. A route only moves down a tier
when its approval rate at the current tier has been ≥95% for
14 days.

**Backout plan.** Set `tier_routing_enabled=False` — every
task routes to `defaults.top_tier`, identical to pre-rollout.
Policy file stays (benign). Expected backout: one config flip,
<1 min.

## Links

- Specs: [0030 — model tier routing](../../product-specs/wip/0030-model-tier-routing.md),
  [observability](../../product-specs/active/observability.md),
  [task-orchestration](../../product-specs/active/task-orchestration.md).
- ADRs: none yet — may need an ADR for "tier-policy lives in
  `template/`, not as a coder-core singleton".
- Services: coder-core (resolver, migrations, metrics API),
  coder-admin (per-tier card).
- Related designs: [0029 — prompt caching](./0029-prompt-caching.md)
  (cache-key interaction),
  [observability-and-cost-tracking](../active/observability-and-cost-tracking.md),
  [worker-roles](../active/worker-roles.md),
  [worker-communication](../active/worker-communication.md).
