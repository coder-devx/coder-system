---
id: '0092'
title: PM and other stage=None tasks must be retriable via override
type: spec
status: wip
owner: ro
created: '2026-05-13'
updated: '2026-05-13'
last_verified_at: '2026-05-13'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- developer-worker
- 0081
parent: pipeline-operations
---

# PM and other stage=None tasks must be retriable via override

**Phase:** wip
**Progress:** 0 / 3 acceptance criteria

## Problem

`POST /v1/projects/{pid}/tasks/{id}/override` rejects any task whose
`stage` is `null` with `409 no_pipeline: task has no pipeline stage
(legacy task)`. That rejection makes sense for genuinely pre-pipeline
historical rows, but it incorrectly catches three live-system cases:

1. **PM tasks created by the founder approve handler.** The cycle-1
   calibration approve flow ([coder-core#236](https://github.com/coder-devx/coder-core/pull/236))
   queues a PM-draft task on the target project with `stage=None`. The
   founder approve loop has no path to dispatch this task into the
   pipeline; on the operator side, neither does override. As of
   2026-05-13 ~06:00 UTC there are five such PM tasks queued for >12h
   (one calibration, four legacy ship-WIP tasks) that the dispatcher
   refuses to pick up and the override path refuses to retry. The
   calibration loop's "approve→PM-draft→spec→architect→implement"
   chain therefore stalls at step 2 after the very first cycle, and
   the dogfood gate can only measure approve-match accuracy — not
   end-to-end loop health.

2. **Architect tasks immediately after spec-run dispatch.** A spec-run
   posted via `POST /v1/projects/{pid}/spec-runs` creates an architect
   task at `stage=None` until the dispatcher claims it (transitions
   to `executing`). If the dispatcher is saturated or restart-stalled
   at that moment, the task sits at `(status=queued, stage=None,
   started_at=null)` and the operator's only recovery is to delete
   and re-create the spec-run — losing the audit trail and the
   spec-run id used by Studio. Spec 0081's dispatcher re-kick is a
   timer-based passive remedy; it doesn't cover the operator wanting
   to retry a specific task on demand.

3. **Team-manager tasks.** Same shape as architect tasks: after
   `POST /spec-runs` the TM task is at `stage=None` until claimed.

Triaging stuck tasks from the admin UI is the operator's primary
"is anything wedged?" lever, so the override path is the natural
single point to fix this.

## Goals

- Make `action: retry` succeed on any queued task regardless of
  pipeline-stage value, as long as the role is one the dispatcher
  currently handles (architect, pm, team-manager, developer, reviewer,
  consultant).
- Preserve the existing 409 for truly legacy tasks: those with
  `role` outside the supported set, or with `pipeline_run_id` set on
  a now-defunct pipeline kind.
- Surface the actual blocker when override rejects: instead of
  "legacy task", say `unknown_role` / `stale_pipeline` / etc. with
  enough detail for the operator to act.

## Non-goals

- Auto-retrying these tasks on a timer — that's spec 0081's job, and
  it's only a partial fix because some retries need an operator
  decision (e.g., "yes drop the stale calibration cycle, don't
  re-fire").
- Changing the founder approve loop to dispatch the PM-draft task
  itself. The right boundary is "approve queues the task; the
  dispatcher (or operator override) starts it" — same as every
  other task created from outside the pipeline.
- Reworking `stage` to be non-nullable. Several legitimate task
  creators (founder approve, spec-run bootstrap, admin Create Task)
  leave `stage` unset until the dispatcher decides what stage applies.

## Scope

Three surfaces:

1. **Override handler** (`src/coder_core/api/task_overrides.py` or
   wherever `_require_pipeline_stage` lives — confirm during design).
   Drop the blanket "stage IS NULL → 409" check. Replace with:
   - If the task's `role` is in the dispatcher's supported set,
     accept the override and treat as a normal `retry` (the
     dispatcher will assign `stage` when it claims the task).
   - If `role` is unrecognized or the task is genuinely orphaned
     (e.g., points at a deleted plan), return a more specific 409
     with `failure_kind: stale_task` and enough metadata for the
     operator to triage.

2. **Dispatcher pickup for stage=None tasks.** The current dispatcher
   loop scans for `(status=queued, stage=executing, started_at=null)`
   as part of spec 0081's re-kick scope. Widen the scan to also
   include `(status=queued, stage IS NULL)` tasks with an eligible
   role. Bounded: limit to N stage-null retries per coordinator tick
   to avoid mass-dispatch on a wedged system.

3. **Admin UI surface.** The pipeline page's per-task "Retry" button
   today disables itself on stage-null rows (it predicts a 409). Lift
   that prediction: render the button enabled for any non-terminal
   row whose role is in the supported set. The 409 case still
   surfaces as a toast on click, which is acceptable noise.

## Acceptance criteria

- **AC1.** `POST /v1/projects/coder/tasks/{calibration-pm-id}/override`
  with `{"action":"retry"}` returns 200 and transitions the task to
  `(stage=executing, started_at != null)` within one coordinator tick.
  Verified end-to-end against the calibration cycle-1 PM task
  `36e0ed61` (or its equivalent on a fresh dogfood run).

- **AC2.** A previously stage-null architect or team-manager task
  also accepts the override and gets claimed within one tick. Verified
  by deliberately saturating the worker pool, dispatching a fresh
  spec-run, observing the stage-null state, and overriding.

- **AC3.** Truly stale tasks (e.g., role outside the dispatcher's
  current support set) still 409 — but with a specific
  `failure_kind` value that names the actual cause (`unknown_role`,
  `orphan_plan`, etc.). Operator-facing error message updates in
  the admin UI accordingly.

## Open questions

- Should the override handler auto-assign `stage` when accepting a
  stage-null retry, or leave that to the dispatcher? Cleaner if the
  dispatcher is the single writer of `stage` — but adds a one-tick
  latency before the operator sees the task move.
- For the calibration PM-draft tasks specifically: do we treat
  them as `stage=pm_draft` (a new pipeline stage) or thread them
  through the existing `executing` stage? Coupling decision; design
  should answer with the simpler path first.
- The four stale ship-WIP PM tasks (`460213bc` / `06b8a8cf` /
  `d4741b75` / `4e07947f`) were queued 2026-05-12 to ship specs
  0075/0077/0079/0080 that have since landed via the operator-led
  Phase A close-out. These are zombies, not retriable work. The
  override 409 in their case is correct *only because* there's no
  way to cancel them either. A `action: cancel` for stage-null
  tasks is the symmetric path — file a sub-spec or fold into this
  one during design.

## Links

- [coder-core#236](https://github.com/coder-devx/coder-core/pull/236) — the founder approve handler that creates the stage-null PM-draft tasks.
- [coder-system spec 0081](system/product-specs/wip/0081-dispatcher-rekick-queued-executing-stuck-tasks.md) — the dispatcher re-kick scope this builds on.
- 2026-05-13 ~06:00 UTC dogfood snapshot: five PM tasks queued at stage=None for 12-21 hours each; calibration cycle-1's PM-draft is one of them.
