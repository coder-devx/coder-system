---
id: '0081'
title: Dispatcher re-kick for tasks stuck at queued/executing with no started_at
type: spec
status: wip
owner: ro
created: '2026-05-12'
updated: '2026-05-12'
last_verified_at: '2026-05-12'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- task-orchestration
- self-healing
parent: pipeline-operations
---

# Dispatcher re-kick for tasks stuck at queued/executing with no started_at

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

When the worker pool is saturated at dispatch time, the dispatcher flips a task row to `status='queued', stage='executing'` but no worker process actually grabs it. `started_at` stays `NULL`. The task then sits idle indefinitely — no later dispatcher tick re-evaluates it, no self-heal pattern reclaims it, no operator-visible failure surfaces. The only working recovery today is for the operator to issue `POST /v1/projects/{id}/tasks/{task_id}/override` with `{"action": "retry"}`, which re-kicks the dispatcher and lets a worker pick it up.

This was observed five times in the Phase A push and is biting actively right now: tasks `4e07947f`, `d4741b75`, `460213bc`, `06b8a8cf` (Studio spec-run kickoff PM tasks from 2026-05-10), plus `36e0ed61` (the PM-draft task dispatched from the calibration cycle 1 approve on 2026-05-12 17:57 UTC) are all sitting in this state across two separate firings days apart.

The cost compounds under Phase B's pressure: every approve dispatched from the Studio idea-queue surface fires a PM-draft task. If the pool happens to be saturated when that dispatch lands, the task is silently orphaned until an operator manually retries it. The Phase B vision is that operator-approval is the only blocking surface; a hidden third blocker (random pool-saturation orphaning) breaks that contract.

## Users / personas

Operators relying on the orchestrator to make forward progress without per-task supervision. Specifically: the Studio-mode operator approving ideas from the idea-queue and expecting PM drafts to fire; the meta-system operator running a calibration burst across multiple spec-runs in parallel.

## Goals

- A task at `(status='queued', stage='executing', started_at IS NULL)` for more than a small grace window is re-evaluated by the next dispatcher tick.
- Re-evaluation either (a) hands the task off to a free worker, or (b) flips it back to `(status='queued', stage='queued')` so the standard dispatch path picks it up.
- The re-kick is idempotent: a task already in flight (started_at populated by a racing worker) is left alone.
- Operator's `action: retry` override remains available as a manual escape hatch, but day-to-day operation does not require it.

## Non-goals

- Changing the pool's concurrency limit. The pool may stay at ≤3 concurrent dev workers; this spec only fixes the dispatcher state machine, not the throughput ceiling.
- Replacing or rewriting the existing self-heal pattern framework. Re-kick is a dispatcher-tick concern, not a self-heal-window concern.
- Changing the semantics of the existing `action: retry` override. The override stays operator-callable for any state.
- Refactoring the dispatcher's broader stage-machine. The fix is bounded to the single transition pair (`queued/executing/started_at=NULL` → re-evaluate).

## Scope

Two surfaces:

1. **Dispatcher coordinator loop** (`coder-core` `coder_core/workers/coordinator.py`): each tick, query for tasks where `status='queued' AND stage='executing' AND started_at IS NULL AND updated_at < now() - <grace_seconds>`. For each match, attempt to re-dispatch into the worker pool. If the pool is still full, flip the stage back to `queued` so the task re-enters the normal dispatch queue without losing its place.

2. **Telemetry + audit** (`coder-core`): emit a structured log line `dispatcher.rekick_stuck_task` with `task_id`, `previous_stage`, `pool_capacity`, and `action_taken` (`re_dispatched` | `flipped_to_queued`). Write an audit event `task.dispatcher_rekick` so operators can see the recovery in the task's audit timeline.

No admin-UI changes are required for this spec. The operator's existing override path continues to work; this spec just removes the need to use it for the pool-saturation case.

### Grace window

The grace window must be long enough that a worker process which has genuinely picked up the task but hasn't yet updated `started_at` is not preempted. Worker spin-up takes seconds, not minutes; 60 seconds is a safe default. Make this configurable via `settings.dispatcher_rekick_grace_seconds` so it can be tuned without a deploy.

## Acceptance criteria

- **AC1.** A task seeded as `(status='queued', stage='executing', started_at=NULL, updated_at=now() - 90s)` is re-evaluated by the next dispatcher tick. The `task.dispatcher_rekick` audit row is written with `action_taken` in `{re_dispatched, flipped_to_queued}` and a structured `dispatcher.rekick_stuck_task` log line is emitted.
- **AC2.** When the worker pool has free capacity at the rekick moment, the task is re-dispatched in place: `started_at` is populated within one tick and `stage` stays `executing`. No second `started_at`-NULL flip is observed.
- **AC3.** When the worker pool is full at the rekick moment, the task's `stage` flips back to `queued` so the next pool-free moment picks it up via the standard dispatch path. No duplicate audit row is written until the next stuck condition.
- **AC4.** A task with a recent `updated_at` (within `dispatcher_rekick_grace_seconds`) is not touched, even if `started_at` is NULL. A task with `started_at` already populated is not touched, regardless of `updated_at`. (Two regression guards: don't preempt healthy worker spin-up, don't kick a task that's actively running.)
- **AC5.** With the rekick in place, manual end-to-end test: dispatch four PM tasks concurrently against a three-worker pool. The fourth lands in `queued/executing/started_at=NULL` initially; within `grace_seconds + tick_interval` it is observed in either `executing/started_at!=NULL` or `queued/queued`. No operator override is required.

## Open questions

- Should the rekick path also handle `(status='queued', stage='executing')` with an old `started_at` (i.e. a worker that started, crashed, and left state stale)? Memory describes this as a distinct failure mode (40-min worker deadline) with its own recovery (`action: resume`). Recommend keeping that out of scope for this spec — different state, different recovery, different acceptance criteria.
- The 60-second grace window is a guess. Should it be lower (the typical worker spin-up is <10s in practice on the existing pool) to recover faster, or higher to absorb cold-start tails? Operator can tune via the settings flag once we have a week of post-deploy data.
- Should the audit row carry a `pool_capacity_at_rekick` field so operators can spot pool-pressure trends? Probably yes; cheap to add.

## Links

- ADR 0028: allocation guard — dispatcher must supply the id, worker must refuse if missing
- Related observation: see `feedback_dispatcher_id_race.md` (ID-allocation race under concurrent dispatch). Different race, same family of dispatcher-tick state-machine gaps.
- Recovery muscle memory: `POST /v1/projects/{id}/tasks/{task_id}/override` with `{"action": "retry"}` remains the manual escape hatch. This spec removes the need to use it for the pool-saturation case but does not deprecate the override surface.
