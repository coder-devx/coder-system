---
id: '0042'
title: Self-healing stuck pipelines
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
served_by_designs: ['0042']
related_specs:
  - task-orchestration
  - observability
  - audit-log
  - admin-panel
  - '0041'
---

# 0042 — Self-healing stuck pipelines

## Problem

A pipeline can get stuck in ways that are _known-safe to fix_ and do
not need human judgement: a task in `queued` status for 20 minutes
when the dispatcher queue is empty; a worker running but not
heartbeating for 5 minutes past its deadline; a pipeline run that
reached `all_dev_tasks_accepted` but the chain hook didn't dispatch
the PM-accept task because of a transient outage.

Today every one of these pages a human via 0041 even though the
remediation is identical every time the operator looks at them: in
the first case, click **Retry**; in the second, kill + clone; in
the third, re-run the chain hook. Waking an operator up at 3 AM to
click a button they've clicked fifty times isn't operator work — it's
automation we haven't written yet.

0041 makes sure humans know when something is wrong. 0042 makes
sure the system tries the safe fixes first, so the human is woken
only when something genuinely needs judgement.

## Users

- **Operator on-call** — wants the rate at which they're paged
  dropped by whatever fraction of stuck-pipelines have a canned
  fix. Wants the admin panel to show "self-heal attempted at T,
  outcome: succeeded" so they can audit what the system did on
  their behalf while they slept.
- **Release manager** — wants a fleet-wide view of self-heal
  attempts so trust grows over time ("this week: 47 attempts, 45
  succeeded, 2 failed → escalated as normal").
- **Escalation watchdog (0041)** — its peer consumer. A 0042
  success should close any open 0041 escalation pointing at the
  same target.

## Goals

- Detect and remediate three pipeline-stuck patterns automatically,
  without human intervention, with each remediation being
  _provably safe_: the worst case is "no change," never "wrong
  change."
- Cut 0041 L1/L2 page rate by the fraction of escalations whose
  root cause is one of the handled patterns. Target: ≥ 30% drop
  in L1+L2 fires on first 30 days, measured per project.
- Every remediation is an `audit_events` row + a
  `self_heal_attempts` row with full before/after context. Nothing
  silent.
- A flag-per-pattern plus a fleet-wide kill switch so a
  misbehaving remediator can be disabled without a deploy.

## Non-goals

- **"Smart" remediation.** The watchdog doesn't _diagnose_ — it
  pattern-matches known shapes. An unfamiliar stall is not a
  "let's try something" opportunity; it falls through to 0041.
- **Remediation of terminal failures.** If a task is `failed` with
  a real error (schema exhaustion, budget exhausted, reviewer
  rejection), 0042 leaves it alone. 0027 transient retry already
  handles the retryable failure class.
- **Cross-run reasoning.** Each remediation is scoped to one
  target (one task, one run, one chain hook). No
  "this run looks like that run from last week" pattern matching.
- **Resolving 0041 escalations whose trigger 0042 _didn't_ cause
  to close.** We only close escalations we remediated. A human ack
  still owns the manual path.
- **Replacing 0027's transient-retry loop.** 0027 is in-worker and
  retries the claude spawn for 429/timeout/DNS. 0042 is out-of-
  worker and retries the task itself when the worker didn't
  finish for structural reasons. Distinct layers.

## Scope

### In scope — the three v1 patterns

Each pattern is a `(detect, remediate, safety_cap)` tuple.

1. **Pattern `stuck_queued`.**
   - **Detect:** `tasks.status='queued'`, `created_at` older than
     `stuck_queued_min_minutes` (default 15), AND the
     DispatcherQueue depth for this project is 0 (via the 0028
     queue-depth endpoint's DB state, not HTTP), AND the global
     `worker_concurrency` limit isn't pinned (queued would be
     normal under contention).
   - **Remediate:** insert a synthetic dispatch via the existing
     `POST /v1/projects/{id}/tasks/{id}/override` with
     `action='retry_dispatch'` (a thin wrapper that re-invokes the
     dispatcher's `enqueue_task` for the same task id — no clone,
     no state reset).
   - **Why safe:** the task is `queued`, the dispatcher just
     didn't pick it up. Re-enqueueing is a no-op if it's already
     queued (DispatcherQueue's per-task idempotency key is the
     task id).

2. **Pattern `zombie_executing`.**
   - **Detect:** `tasks.status='executing'`,
     `tasks.heartbeat_at` (new, see design) older than
     `zombie_heartbeat_staleness_seconds` (default 180), AND the
     task's configured deadline has elapsed, AND the Cloud Run
     revision hosting the worker is still alive (we don't want to
     remediate during a fleet rollout).
   - **Remediate:** transition the task to `failed` with
     `failure_kind='zombie'` (new kind), then call the existing
     `POST /tasks/{id}/retry` endpoint which clones into a fresh
     queued task preserving the same `spec_id`, `role`, `prompt`.
   - **Why safe:** deadline has elapsed + heartbeat gone =
     whatever process was running is dead or wedged. The `retry`
     clone is the same flow an operator would run manually, same
     audit shape.

3. **Pattern `orphan_chain_hook`.**
   - **Detect:** a `pipeline_runs` row whose step is
     `all_dev_tasks_accepted` and whose next-step task
     (`pm_accept` role in this case) doesn't exist _and_ the
     close-cycle backstop from 0044 (`on_all_dev_tasks_accepted`)
     logged a failure to the structured feed in the last hour.
     Other chain hooks (spec→architect, design→tm) are symmetric.
   - **Remediate:** replay the chain hook via a new internal
     endpoint `POST /v1/_admin/pipeline-runs/{id}/replay-chain`
     that idempotently re-runs `on_<step>_transition` for the
     current step. Idempotency is enforced because the hook's
     first step is "does the next-step task exist? if yes, no-op."
   - **Why safe:** the hook is pure — it reads DB state, creates
     the next task if absent. Running twice on a healthy run
     yields zero side effects (the task exists and nothing changes).

### Safety caps (every pattern)

- **One attempt per target per pattern per day.** A second
  `stuck_queued` detection on the same task within 24 h is logged
  as `skipped_cap` and no remediation fires. Escalation from 0041
  takes over.
- **Fleet kill switch + per-pattern flag.**
  `CODER_SELF_HEALING_ENABLED` is the master; each pattern has its
  own `SELF_HEAL_PATTERN_{NAME}_ENABLED` so a flaky remediator can
  be disabled independently.
- **Dry-run mode** per pattern. `SELF_HEAL_PATTERN_{NAME}_MODE`
  ∈ {`off`, `dry_run`, `apply`}. In `dry_run` the remediator
  runs `detect` and records a `self_heal_attempts` row with
  `outcome='dry_run'` but performs no state change. Used during
  soak.

### In scope — integration with 0041

- On successful remediation, the watchdog looks up open
  `escalations` rows whose `pipeline_run_id` or `task_id` matches
  the remediation target and whose `trigger_kind` corresponds to
  the pattern (see design for the mapping); it calls
  `POST /v1/projects/{id}/escalations/{id}/resolve` with
  `resolved_by_type='system'`,
  `resolved_by_id='self-healing-watchdog'`,
  `resolution='<pattern> remediated'`.
- On failed or skipped remediation, no escalation action — the
  0041 watcher will advance as normal on the next tick.

### Out of scope

- Any pattern not in the three-pattern list. Adding a pattern in
  v1 is a separate WIP; v1 builds the registry + harness, v2+
  grows the catalog.
- Auto-remediating reviewer `request_changes` verdicts.
- Pausing / resuming / cancelling _pipeline runs_ as a
  remediation. Only task-level and chain-hook operations in v1.
- Cross-project remediation. Watchdog runs scoped per project
  (single transaction per project per tick).

## Acceptance criteria

- **AC1.** `self_heal_attempts` table exists with columns for
  pattern, target, attempted_at, outcome (`succeeded | failed |
  skipped_cap | dry_run`), detail JSONB, and a FK to the
  remediation's `audit_events` row.

- **AC2.** Registry of three `Remediator` implementations
  (`stuck_queued`, `zombie_executing`, `orphan_chain_hook`) with
  a uniform `detect + remediate` interface and one-line
  registration in `REMEDIATORS`.

- **AC3.** Watchdog Cloud Run Job `coder-core-self-heal-watch`
  ticks every 5 min, runs all enabled remediators per project,
  respects the per-pattern mode + the fleet flag.

- **AC4.** Per-target-per-pattern-per-day cap enforced by a
  lookup into `self_heal_attempts` before each remediation. Hit
  → record `skipped_cap` row, no action.

- **AC5.** `tasks.heartbeat_at` column exists (migration); role
  workers update it every 30 s during execution via a new
  `PATCH /v1/projects/{id}/tasks/{id}/heartbeat` endpoint
  (impersonation-token-auth).

- **AC6.** Every remediation writes an `audit_events` row with
  `action='self_heal.remediated'`, the pattern name, the target
  reference, before/after snapshot. Failed remediations write
  `action='self_heal.failed'`.

- **AC7.** On remediation success, the watchdog enumerates open
  escalations matching the target and closes each via the
  `/escalations/{id}/resolve` endpoint with
  `resolved_by_id='self-healing-watchdog'`.

- **AC8.** Flag gating: `CODER_SELF_HEALING_ENABLED` master off
  by default; each pattern flag
  `SELF_HEAL_PATTERN_{NAME}_MODE`=`off` by default.

- **AC9.** Admin `/admin/self-heal` page lists recent attempts
  across the fleet with pattern, target, outcome, and links to
  the closed escalation (if any). Behind
  `VITE_SELF_HEAL_ENABLED`.

- **AC10.** Dry-run shadow mode produces metrics without side
  effects, used for the 1-week soak in rollout stage 1.

- **AC11.** Runbook `system/runbooks/self-heal-misfire.md` exists
  and documents: how to disable a single pattern, how to disable
  the fleet, how to audit a specific attempt, how to manually
  revert a remediation (by re-running the dispatcher / hand-
  creating the next task, etc.).

## Metrics

- **Per-pattern attempt rate** — detections per week per
  project. Feeds tuning.
- **Per-pattern success rate** — `succeeded / (succeeded +
  failed)`. Target ≥ 95% per pattern; below 90% is a signal the
  detector is too loose and the pattern should be tightened or
  disabled.
- **Escalations prevented** — count of `escalations` rows
  resolved by `self-healing-watchdog`, per week, per project.
  The headline KPI.
- **Mean time from stuck → remediated** — `detected_at -
  target_became_eligible_at`. Target ≤ 6 minutes (1 tick +
  detection slack).
- **False-positive rate** — dry-run attempts where the target
  _resolved itself_ between detection and the next tick
  (measured by comparing the detection set across consecutive
  ticks). High false-positive rate on a pattern → raise the
  detection window.

## Open questions

- **Heartbeat adoption.** `tasks.heartbeat_at` is new. Workers
  (PM, Architect, TM, Developer, Reviewer) need to update it
  periodically. Is every worker retrofit happening in one PR, or
  do we rely on a supervisor wrapper? Leaning: a supervisor
  wrapper in `coder_core/workers/_runtime.py` that each worker's
  entry point already goes through (same place `run_with_transient_retry`
  lives). Design should pin this.

- **Chain-hook replay safety.** Claim: the hook is pure / no-op
  on re-run. Is this actually true across all four chain points
  (spec→architect, design→tm, plan→developer fan-out,
  all_dev_accepted→pm_accept)? Each has a uniqueness check on the
  would-be-created child task, but the design should enumerate
  and assert. If any hook is not idempotent, we don't ship its
  replay in v1.

- **Per-pattern `apply` rollout ordering.** `stuck_queued` is the
  lowest-risk and highest-value; should it go to `apply` first
  while others stay `dry_run`? Yes, probably — spec defers the
  ordering to the rollout plan but open-questions it here.

- **Do zombie-remediations clone prompts with the shared context
  block from 0029?** A cloned task re-materialises its project
  context; the new run gets a fresh `pipeline_run_id` context
  block. Should it inherit the original's? Leaning: yes, because
  the original's context was what the operator approved. Design
  should define.

- **Observability hook mapping.** 0041 has three trigger kinds;
  we have three patterns. Is the mapping one-to-one or
  one-to-many? Reality: one pattern can satisfy multiple
  triggers (e.g. a `zombie_executing` can show up as both a
  stall and a failure-streak). Design needs to define which
  triggers a given remediation closes.

## Links

- Related specs:
  [task-orchestration](../active/task-orchestration.md),
  [observability](../active/observability.md),
  [audit-log](../active/audit-log.md),
  [admin-panel](../active/admin-panel.md),
  [0041](./0041-escalation-policies.md)
- Design: [0042](../../designs/wip/0042-self-healing.md)
- Roadmap entry: [ROADMAP.md](../ROADMAP.md) → Phase 7 / 0042
