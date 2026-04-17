---
id: pipeline-run-blocked
title: Pipeline run blocked on a human gate — operator triage
type: runbook
status: active
owner: ro
created: 2026-04-17
updated: 2026-04-17
last_verified_at: 2026-04-17
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: []
---

# Pipeline run blocked on a human gate

Operational guide for runs sitting in a `spec_approval`,
`design_approval`, or `plan_approval` step. These are the three
places where the pipeline stops and waits for a human. The admin
Runs list sorts blocked runs to the top and stamps each with a
`blocked Nm` red badge (spec
[0026](../product-specs/wip/0026-pipeline-run-dashboard.md)); the
`RunDetail` page renders an inline Gate card once opened.

## When to run this

- A run's "blocked Nm" badge exceeds your team's gate-SLA
  (suggested: 15 min for spec/design, 30 min for plan).
- A project owner pings that "their pipeline is stuck".
- Fleet-level: more than ~5 blocked runs sitting simultaneously
  is a signal that the gate cadence isn't matching pipeline
  throughput — the operator should triage in one sweep.

## Who can run this

Operator with admin JWT, or the project owner via their own
project API key. Approve/reject goes through the standard
`POST /knowledge/{type}/{id}/{approve,reject}` or
`POST /task-plans/{id}/{approve,reject}` endpoints; no new
authority is created by the Gate card UX.

## What the Gate card shows

Three variants depending on `run.current_step`:

| Step | Underlying endpoint | Gate card action |
|---|---|---|
| `spec_approval` | `POST /knowledge/specs/{id}/{approve,reject}` | Inline Approve / Request changes / Reject |
| `design_approval` | `POST /knowledge/designs/{id}/{approve,reject}` | Inline Approve / Request changes / Reject |
| `plan_approval` | `POST /task-plans/{id}/{approve,reject}` | Drills to PlanDetail (inline editing is a Phase 5 follow-up) |

"Request changes" calls the reject endpoint with a synthetic
`request-changes:` prefix on the feedback body. Revision tasks
scheduled against rejected specs/designs key off that prefix when
deciding whether to respawn the originating worker.

## Triage

1. **Open the Runs list.** The blocked-longest-first sort means
   the top of the table is "what needs you first." Scan the
   `blocked Nm` badges and note anything over your gate SLA.
2. **Click into the blocked run.** `RunDetail` mounts the Gate
   card at the top. The step chip plus the card title tell you
   which gate type (spec / design / plan).
3. **Read the artifact.** The Gate card embeds (or links to) the
   pending artifact. For spec/design that's the markdown +
   acceptance criteria; for plan that's the task list.
4. **Classify the outcome.** Five patterns:

### Outcome A — Approve

Artifact looks correct. Click **Approve**.

- Endpoint: `POST /knowledge/{type}/{id}/approve` (spec/design)
  or `POST /task-plans/{id}/approve` (plan).
- Pipeline advances automatically: the `advance_step` helper
  clears `blocked_since`, sets `step_started_at`, and moves
  `current_step` to the next phase. `pipeline_run.changed` SSE
  event fires; the Runs list re-sorts without a refresh.

### Outcome B — Request changes

Artifact is directionally right but needs a specific edit. Type
the ask in the feedback textarea and click **Request changes**.

- Endpoint: `POST /knowledge/{type}/{id}/reject` with body
  `request-changes: <your ask>`.
- The worker that produced the artifact (PM for specs,
  Architect for designs, TM for plans) re-runs with your
  feedback prepended; a new artifact appears and the gate
  reopens. The run stays in the same `*_approval` step; its
  `blocked_since` is refreshed.

### Outcome C — Reject

Artifact is wrong-enough that editing is worse than starting
over, or the underlying feature doesn't belong in the roadmap.
Type the reason and click **Reject**.

- Endpoint: `POST /knowledge/{type}/{id}/reject` with body
  `<your reason>` (no prefix).
- Pipeline run transitions to a rejected terminal state. The PM
  for accept / PM for draft (case depending) gets the reason on
  the `task_messages` thread; no follow-up task is scheduled.

### Outcome D — Plan approval needs editing first

Plan approval's Gate card doesn't approve inline — it drills to
the Plan Detail page because the operator usually wants to
edit the task list (reorder, re-prompt, drop) before approving.

- Click **Open plan** on the card → `PlanDetail` page.
- Edit inline, then approve or reject from there.
- Returning to the run view shows the pipeline advanced.

### Outcome E — The run is stuck, not blocked

`blocked_since` is null but the Runs list still shows the run
in a non-terminal state with no recent updates. This isn't a
gate problem — it's an orphan or a hung worker.

- Check [worker-transient-failure](./worker-transient-failure.md)
  for transient-retry exhaustion.
- If the task row has an open stage past its per-role deadline,
  the orphan reaper (ADR 0011) should kick in on the next
  poll — wait 30–60 s, then re-dispatch manually if the
  reaper didn't.

## Success condition

- The run's `blocked_since` clears and `current_step` advances
  (or the run reaches a terminal state via Reject).
- The admin Runs list no longer shows the red badge for this
  run, and the sort re-orders away from the top.
- Per-project gate-SLA metric (median time spent in
  `*_approval`) holds below target after a week of using the
  inline Gate card vs the old out-of-page approval flow.

## If something goes wrong

- **Approve button returns 409.** Concurrent approve from a
  second operator. The card's error panel shows the 409; a
  manual refresh pulls the latest state and the gate is usually
  already cleared.
- **Approve button returns 422 "artifact not found".** The
  underlying spec/design was deleted out-of-band. The card
  disables Approve and exposes Reject + Cancel run. Finish by
  cancelling the run.
- **Gate card renders but the pipeline doesn't advance after
  Approve.** The `advance_step` write succeeded but
  `on_spec_approved` / `on_design_approved` didn't fire —
  usually a disabled chain hook. Check
  [task-orchestration](../product-specs/active/task-orchestration.md)'s
  pipeline-chaining section and the worker logs for the approve
  call.
- **Request-changes isn't respawning the worker.** The
  `request-changes:` prefix parsing is server-side; check that
  the feedback you sent actually starts with that literal
  prefix (the Gate card adds it automatically). If it still
  isn't working, check the PM/Architect worker's revision hook.

## Related

- Spec: [0026 — pipeline run dashboard](../product-specs/wip/0026-pipeline-run-dashboard.md)
- Design: [0026 — pipeline run dashboard](../designs/wip/0026-pipeline-run-dashboard.md)
- Related specs:
  [task-orchestration](../product-specs/active/task-orchestration.md)
  (pipeline chaining + approval endpoints);
  [admin-panel](../product-specs/active/admin-panel.md) (Runs list
  + RunDetail pages).
- Adjacent runbooks:
  [worker-transient-failure](./worker-transient-failure.md),
  [concurrency-overflow](./concurrency-overflow.md).
