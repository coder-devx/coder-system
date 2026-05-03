---
id: '0064'
title: 'Schema-gate recovery: persist and replay exhausted worker output'
type: spec
status: wip
owner: ro
created: '2026-05-03'
updated: '2026-05-03'
last_verified_at: '2026-05-03'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- task-orchestration
- observability
parent: pipeline-operations
---

# Schema-gate recovery: persist and replay exhausted worker output

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

When a PM, Architect, or Team Manager worker exhausts the strict-JSON
compliance retry budget, the orchestrator marks the task `failed` with
`failure_kind="schema"`. Today only a truncated snippet of the last
attempt's raw output survives in `failure_detail`. The full output —
which may be a near-complete spec, design, or plan needing only cosmetic
repair — is discarded. Operators have no way to inspect, hand-edit, or
resubmit it. The pipeline stalls and the model's work is silently gone.

## Users / personas

Operators using the admin panel's task detail view who find a pipeline
stalled on a `failed` task with `failure_kind="schema"` and need to
recover the work without re-running the full worker from scratch.

## Goals

- The full, untruncated raw output from the last gate-exhaustion attempt
  is persisted and readable from the admin panel without a log dive.
- Operators can submit a hand-edited version of that raw output back
  through the validation gate from the admin panel.
- A gate-replay that passes validation transitions the task and runs
  Phase 4 side-effects exactly as the original worker path would have.
- No PM draft, architect design, or TM plan is silently lost because of
  a formatting failure.

## Non-goals

- Automatic or AI-assisted output repair (the existing retry loop already
  re-prompts; this spec is the human-recovery path after that fails).
- Persisting intermediate retry attempts (only the final exhausted
  attempt matters for recovery).
- Changing the retry budget, gate logic, or re-prompt strategy.
- Pre-populating a new task's prompt from held output (operators can
  read the held output and author a follow-up task manually).

## Scope

- New nullable column `tasks.raw_output_held` (TEXT) populated at the
  moment `failure_kind="schema"` is set on gate exhaustion; removes the
  truncation that currently applies to `failure_detail`'s raw snippet.
- New endpoint `POST /v1/projects/{id}/tasks/{task_id}/gate-replay`
  accepting `{"raw_output": "..."}`: runs the task's role-specific schema
  validator, returns errors on failure (task state unchanged), or
  transitions the task and runs Phase 4 on success.
- Admin task detail page: for `failure_kind="schema"` tasks, render the
  full `raw_output_held` in a scrollable read-only code block and expose
  a "Replay gate" action that opens an editable textarea pre-populated
  with the held output and a Submit button wired to the replay endpoint.
- Structured log events `worker_output_compliance.gate_replay.{attempted,
  passed,failed}` through the existing observability feed.
- Successful replays recorded in `task_stage_runs` with
  `stage="schema_replay"` for audit continuity.

## Acceptance criteria

- [ ] AC1: A PM/Architect/TM task that exhausts the compliance retry
  budget stores its full, untruncated last-attempt raw output; the text
  is retrievable via `GET /v1/projects/{id}/tasks/{task_id}` (new
  `raw_output_held` field) with no length cap.
- [ ] AC2: The admin task detail page for a `failed` + `failure_kind=
  "schema"` task renders the complete raw output in a scrollable code
  block — no SSH or Cloud Run log access required.
- [ ] AC3: The admin task detail page shows a "Replay gate" action for
  schema-failed tasks; clicking it opens an editable textarea
  pre-populated with `raw_output_held` and a Submit button.
- [ ] AC4: Submitting a gate-replay with output that passes schema
  validation transitions the task out of `failed`, runs Phase 4
  side-effects (artifact write + registry update), and the admin panel
  reflects the updated task state within one SSE cycle.
- [ ] AC5: Submitting a gate-replay with still-invalid output returns
  the validation errors inline and leaves the task in `failed` with no
  state change and no duplicate side-effects.

## Open questions

- Should `raw_output_held` live on the `tasks` table (nullable TEXT,
  simpler, avoids a join) or in a separate `task_held_outputs` table
  (allows multiple snapshots per task)? Recommend the column for v1.
- Should a successful gate-replay be idempotent if submitted twice with
  the same payload? Recommend yes — Phase 4 registry writes are
  already idempotent for append operations.
- Does the replay endpoint need a separate permission scope, or does the
  existing operator-level project access cover it?

## Links

- Related specs: [task-orchestration](../active/task-orchestration.md),
  [observability](../active/observability.md)
- Runbook: [worker-schema-failure](../../runbooks/worker-schema-failure.md)
