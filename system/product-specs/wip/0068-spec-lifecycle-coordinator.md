---
id: '0068'
title: 'Spec-lifecycle coordinator: auto-chain PM → Architect → TM transitions'
type: spec
status: wip
owner: ro
created: '2026-05-03'
updated: '2026-05-03'
last_verified_at: '2026-05-03'
deprecated_at: null
reason: null
served_by_designs:
- '0068'
related_specs:
- task-orchestration
- observability
- escalations
- multi-tenancy
- admin-panel
- audit-log
parent: pipeline-operations
---

# Spec-lifecycle coordinator: auto-chain PM → Architect → TM transitions

**Phase:** wip
**Progress:** 0 / 9 acceptance criteria

## Problem

Once a PM-drafted spec is accepted, three human button-presses stand
between it and the developer fleet starting work: spawn the architect
task, spawn the team-manager task, approve the plan. Today the spec
parks at each handoff until a human happens to be watching the admin
panel. Throughput from spec-accept to first developer dispatch is
measured in hours-to-days, dominated by human dispatch latency rather
than the actual worker time.

The close-cycle backstop in `pipeline_chain.py` (per
ADR [0015](../../adrs/0015-ship-gate-in-coder-pipeline.md)) already
automates the *last* transition — when all task plan rows complete and
all ACs are satisfied, the architect ship-draft and reviewer
ship-attestation are auto-dispatched without a human spawn. The same
pattern, generalized one level up, would eliminate the three earlier
manual spawns and let a spec progress end-to-end on its own — pausing
only at the three intentional human-judgment gates (PM-accept, plan
approve, ship-merge).

This spec is that generalization: a per-spec lifecycle state machine
with auto-dispatch on transitions, circuit breakers to prevent
runaway, and explicit pause / resume controls.

## Users / personas

- **Operators** who currently watch the admin panel and click "spawn
  architect" / "spawn team manager" / "approve plan" between stages.
  After this ships, they review at the three retained gates and
  intervene only when the coordinator pauses.
- **Project owners** who want predictable spec-to-shipped throughput
  and a single place to see "where is each in-flight spec right now."
- **On-call engineers** who today have to dig through individual
  task rows to know whether a spec is genuinely stuck or just waiting
  for a human spawn.

## Goals

- A spec progresses automatically from `accepted` through `designing`,
  `design_landed`, `planning`, `plan_pending`, `implementing`,
  `ship_pending`, `shipped` — without human intervention at the
  *spawn* points.
- Three explicit human gates preserved unchanged: PM accept (decides
  the problem is right), plan approve (decides the breakdown is
  right), ship merge (decides the WIP→active fold is right).
- Median time from PM-accept verdict to first developer task dispatch
  drops from "next time a human looks" to ≤ 5 minutes.
- A single admin-panel view per project shows every in-flight spec's
  current state, last transition timestamp, current task, and
  pause-on-circuit-breaker reason if any.
- Circuit breakers (per-stage retry cap, per-spec cost cap, stuck-
  stage threshold) prevent the kind of cascading-bad-output failure
  modes that automation introduces.

## Non-goals

- Replacing PM-accept, plan-approve, or ship-merge as quality gates —
  those decisions stay with humans.
- Auto-approving low-confidence plans — covered by spec
  [0040](./0040-confidence-auto-approve.md). This spec consumes 0040's
  output; it doesn't duplicate it.
- Auto-recovering from schema-gate exhaustion — covered by spec
  [0064](./0064-schema-gate-recovery-persist-and-replay-exhausted-worker-output.md).
  When 0064 lands, the coordinator hands off to its replay path
  instead of pausing.
- Cross-spec scheduling, priority queue, or fleet-wide concurrency
  caps. The coordinator is per-spec; concurrency stays at the worker
  level.
- Replacing the existing per-task orchestrator (the developer →
  reviewer → fix-loop chain inside `implementing`). The coordinator
  *delegates* to the orchestrator; it does not re-implement worker
  dispatch.

## Scope

**Lifecycle states.** A spec_run progresses through:

```
draft  → accepted  → designing  → design_landed  → planning
       → plan_pending  → implementing  → ship_pending  → shipped
       → (terminal)
```

Plus terminal exits: `deprecated` (PM rejected) and `paused` (any
state, set by circuit breaker or operator action).

**Database — `spec_runs` table (new migration).** Columns:
- `id uuid PK`
- `project_id text NOT NULL FK projects(id)`
- `wip_spec_id text NOT NULL` — the numeric WIP id (`0061`)
- `state text NOT NULL` — one of the lifecycle states above
- `current_task_id uuid NULL FK tasks(id)` — the latest dispatched
  task at the current stage
- `paused_reason text NULL` — `cost_cap`, `retry_cap`,
  `manual`, `stuck`, or null
- `cost_input_tokens bigint NOT NULL DEFAULT 0`
- `cost_output_tokens bigint NOT NULL DEFAULT 0`
- `stage_retry_counts jsonb NOT NULL DEFAULT '{}'` — `{state: count}`
  for circuit-breaker enforcement
- `created_at timestamptz NOT NULL DEFAULT now()`
- `updated_at timestamptz NOT NULL DEFAULT now()`
- Unique on `(project_id, wip_spec_id)` — one run per spec per
  project.
- Indexes on `(project_id, state)` for the admin-panel rollup.

**Transition hooks (already-emitting events, new consumers).** The
coordinator does not poll workers; it reacts to the same write events
the workers already emit:
- *PM accept verdict written* → coordinator advances `accepted` →
  `designing` and dispatches a `role=architect` task with
  `prompt: design: <wip_spec_id>`.
- *Architect Phase 4 writes `designs/wip/<wip_spec_id>-…md`* →
  coordinator advances `designing` → `design_landed` →
  dispatches a `role=team-manager` task.
- *TM Phase 4 writes `task_plan` rows* → coordinator advances
  `planning` → `plan_pending` and **stops** (human or 0040
  auto-approves).
- *Plan approved* (human via admin OR 0040 confidence path) →
  coordinator advances `plan_pending` → `implementing`. The existing
  per-task orchestrator takes over from here unchanged.
- *All AC tasks done* → existing `pipeline_chain.py` close-cycle
  fires the ship-gate sequence (already shipped). Coordinator
  observes the transition for state tracking but does not
  re-dispatch.

**Coordinator process.** A new Cloud Run Job
`coder-core-spec-coord-tick` running every 60 seconds. Reads
`spec_runs` rows in actionable states and fires the relevant
transition. Idempotent — a second tick on the same row sees the
already-advanced state and is a no-op. Same pattern as the existing
self-heal-tick and auto-approve-tick.

**Circuit breakers.**
- *Per-stage retry cap.* Default 3. If a stage's task dispatch
  fails (worker errors, schema-gate exhaustion, transient retries
  exhausted), `stage_retry_counts[state]` increments. Hitting the
  cap pauses the spec_run with `paused_reason="retry_cap"` and
  opens an L0 escalation per [escalations](../active/escalations.md).
- *Per-spec cost cap.* Default $50 input + output tokens, configurable
  per project. Hitting the cap pauses with `paused_reason="cost_cap"`.
  Depends on spec [0031](./0031-token-budgets.md) for the underlying
  accounting; ships standalone with a soft cap if 0031 is not yet
  live.
- *Stuck-stage threshold.* Same `sla_stall_minutes` the escalations
  watcher uses. A spec_run with no state change for ≥ threshold opens
  an L0 escalation; if the watcher resolves the stuck task, the
  coordinator picks up where it left off on the next tick.

**Admin panel.** A new "Specs" page at `/projects/:id/specs`
listing every active spec_run with: WIP id, title, state, last
transition timestamp, current task ID + role, paused reason if any,
cumulative cost. Per-row Pause / Resume buttons (admin scope). Click-
through opens the existing pipeline detail view for that spec's task
plan.

**API.**
- `GET /v1/projects/{id}/spec-runs?state=…` — list, filtered.
- `GET /v1/projects/{id}/spec-runs/{wip_spec_id}` — detail, including
  transition history.
- `POST /v1/projects/{id}/spec-runs/{wip_spec_id}/pause` — operator
  pause, sets `paused_reason="manual"`.
- `POST /v1/projects/{id}/spec-runs/{wip_spec_id}/resume` — clears
  pause; coordinator picks up on next tick.

**Audit.** Every state transition emits `spec_run.transitioned`
with `from_state`, `to_state`, `trigger` (the event that caused it),
and `task_id` (the task dispatched, if any). Pause / resume emit
`spec_run.paused` and `spec_run.resumed` carrying actor and reason.

**Backwards compatibility.** Manually-spawned architect or TM tasks
(the existing operator workflow) continue to work. The coordinator
detects "task already exists for this stage" via the same idempotency
check `pipeline_chain.py` uses for ship-draft dispatch and records the
manual spawn in `spec_runs` as a `trigger="manual_override"` audit
event.

## Acceptance criteria

- [ ] AC1: A PM-accept verdict written on a draft spec advances the
  matching `spec_runs.state` from `accepted` to `designing` within
  one coordinator tick (≤ 60 s) and dispatches a `role=architect`
  task with `prompt: design: <wip_spec_id>`. No human spawn needed.
- [ ] AC2: An architect Phase 4 commit landing
  `designs/wip/<wip_spec_id>-…md` (visible via the design registry)
  advances state from `designing` → `design_landed` → `planning`
  within one coordinator tick and dispatches a `role=team-manager`
  task.
- [ ] AC3: A team-manager Phase 4 write of `task_plan` rows
  advances state from `planning` to `plan_pending`; the spec_run
  remains in `plan_pending` until either a human approve OR a
  spec-0040 confidence auto-approve advances it to `implementing`.
- [ ] AC4: Per-stage retry cap (default 3) on a single state, when
  exceeded by repeated dispatch failures, pauses the spec_run with
  `paused_reason="retry_cap"` and opens an L0 escalation visible in
  `/projects/:id/escalations`.
- [ ] AC5: Per-spec cost cap (default $50, project-configurable)
  hit during automated progression pauses the spec_run with
  `paused_reason="cost_cap"`; resume requires explicit operator
  action.
- [ ] AC6: `POST .../pause` and `POST .../resume` work as expected:
  a paused spec_run does not auto-advance even when its transition
  event would otherwise fire on the next tick; a resumed spec_run
  picks up at the state it was paused in without re-dispatching the
  in-flight task.
- [ ] AC7: Every state transition writes one
  `spec_run.transitioned` audit row carrying `from_state`,
  `to_state`, `trigger`, and the dispatched `task_id` (when
  applicable); operators can reconstruct the full lifecycle of any
  spec from the audit log alone.
- [ ] AC8: A manually-spawned architect or TM task (legacy operator
  workflow) is reflected in `spec_runs` within one coordinator tick
  with `trigger="manual_override"` audit, and the coordinator does
  not double-dispatch.
- [ ] AC9: The admin `/projects/:id/specs` page renders every active
  spec_run with state, last transition timestamp, current task ID,
  cost-to-date, and paused reason if any; pause / resume buttons are
  present and gated to admin scope.

## Metrics

- **Median spec-accept-to-first-developer-dispatch latency** (target:
  ≤ 5 min, down from "next time a human looks").
- **Fraction of specs that progress end-to-end without operator
  intervention** between PM-accept and ship-gate panel
  (target: ≥ 70%).
- **Per-spec mean cost** by stage. Surfaces which stages dominate
  spend; informs the cost cap default.
- **Coordinator tick lag.** Time from transition-event-write to
  state-advance. Target ≤ 60 s.
- **Pause-by-circuit-breaker rate per project.** Spike indicates
  cap mistuned or upstream regression; alertable separately.
- **Manual-override rate.** A high rate after this ships means the
  coordinator is missing transitions or operators don't trust it.

## Open questions

- **Cost cap shape.** Flat per-spec ($50) or scaled by estimated
  complexity (e.g., $X per AC, capped at $Y)? Recommend flat for v1;
  revisit after a soak shows whether complex specs starve.
- **Eager vs lazy advance.** Should the PM-accept-verdict write hook
  *directly* update `spec_runs.state` (eager — no tick lag) or only
  emit an event the coordinator polls (lazy — single source of state
  ownership)? Recommend lazy for v1: simpler ownership, tick lag is
  acceptable, easy to upgrade to eager later.
- **Cron tick vs Postgres `LISTEN/NOTIFY`.** Cron is consistent with
  every other recurring job; LISTEN/NOTIFY would shave the ≤ 60 s tick
  lag. Recommend cron for v1; revisit if AC1's 60 s budget becomes
  a real bottleneck.
- **Hand-editing during flight.** What happens when a human edits
  `wip/spec.md` while the coordinator has already dispatched the
  architect? Recommend: edit lands in git, architect's reads of the
  spec see the new content; the coordinator is unaware. If the edit
  changes ACs materially, operator pauses the spec_run and re-runs
  from `accepted`. Document the workflow in the runbook.
- **Multi-WIP specs.** Some WIPs span multiple files (a spec + an
  ADR); should `spec_runs` key on the *spec* file specifically, or on
  a logical "WIP cycle" identifier? Recommend: spec-file-keyed for
  v1; add a `wip_cycle_id` later if multi-file WIPs become common.

## Links

- Active infra: [task-orchestration](../active/task-orchestration.md),
  [observability](../active/observability.md),
  [escalations](../active/escalations.md),
  [self-healing](../active/self-healing.md),
  [admin-panel](../active/admin-panel.md),
  [audit-log](../active/audit-log.md),
  [multi-tenancy](../active/multi-tenancy.md),
  [pipeline-operations](../active/pipeline-operations.md)
- Sibling WIPs: [0040](./0040-confidence-auto-approve.md) (auto-approve
  for plan_pending → implementing), [0031](./0031-token-budgets.md)
  (cost-cap accounting),
  [0054](./0054-orchestrator-github-state-reconciliation.md)
  (state-drift discipline this coordinator should mirror),
  [0056](./0056-worker-dispatch-durability.md) (durable worker
  dispatch the coordinator depends on),
  [0064](./0064-schema-gate-recovery-persist-and-replay-exhausted-worker-output.md)
  (recovery path the coordinator hands off to)
- Predecessor: ADR [0015](../../adrs/0015-ship-gate-in-coder-pipeline.md)
  established the auto-dispatch pattern this spec generalizes.
