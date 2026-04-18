---
id: task-orchestration
title: Task orchestration
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-18
last_verified_at: 2026-04-18
served_by_designs: [worker-communication]
related_specs: []
---

# Task orchestration

## What it is

The state machine and control plane that moves a task from `queued` all
the way to `accepted` — through enrich, execute, test, review, and
acceptance — with automatic fix loops on failure, structured messages
between workers, human approval gates on the knowledge artifacts that
feed the pipeline, one-click retries on terminal failures, and automatic
chaining between pipeline steps so a single problem statement flows from
PM draft to shipped code without a human creating each subsequent task.
Everything in this component runs out of `workers/orchestrator.py` and
the surrounding `/tasks`, `/messages`, `/retry`, `/approve`/`/reject`,
and `/pipeline-runs` endpoints in `coder-core`.

## Capabilities

- **Stage machine.** Tasks advance through `queued → enriched →
  executing → testing → reviewing → accepted | rejected | failed`.
  Every transition is logged with `task_id`, `from_stage`, `to_stage`,
  and timestamp.
- **Fix loops.** On failure, the orchestrator prepends `fix_context`
  (error + failing output + recent worker messages) to the prompt and
  retries from `executing`, up to 3 attempts before moving to `failed`.
- **Worker messages.** Workers and humans exchange structured messages
  on a task (`from_role`, `to_role`, `msg_type` of feedback / question /
  decision / override, optional `verdict` of approve / request_changes
  / reject, free-form `body`). The reviewer's `request_changes` verdict
  routes the task back into the developer fix loop.
- **Human override.** At any stage, operators can pause, resume, retry,
  skip to a stage, or reject a task. Overrides land in the message
  thread for audit.
- **One-click retry.** Failed, timed-out, or stuck tasks can be cloned
  into a fresh queued task that preserves `role`, `prompt`, `repo`, and
  `spec_id`, resets execution state, and links back via
  `original_task_id`. Non-terminal tasks are refused with `422`.
- **Approval gates.** Specs and designs drafted in `wip/` have formal
  approve/reject endpoints. Approve promotes the artifact to `active/`
  (frontmatter, file move, registry update) and publishes
  `knowledge_approved`. Reject records feedback and can spawn a PM or
  Architect revision task.
- **Stage-run archive.** Every dispatch snapshot lands in
  `task_stage_runs` before the next handler resets the live `TaskRow`
  (migration 0018). The archive is queryable per task via
  `GET /v1/projects/{id}/tasks/{task_id}/stage-runs`, chronologically
  ordered, with `stage` / `status` filters — the replay trail for
  debugging a task without reading Cloud Run logs.
- **Pipeline chaining.** A `pipeline_run` row tracks an end-to-end flow
  for one spec. Approving a spec auto-creates an Architect task;
  approving a design auto-creates a TM task; all developer tasks for a
  spec reaching `accepted` auto-creates a PM acceptance task. Paused
  runs stop chaining until resumed.
- **Worker output compliance.** PM, Architect, and Team Manager worker
  outputs are validated against per-worker JSON schemas (`pm_draft`,
  `pm_accept`, `architect`, `team_manager`) before any Phase 4 side
  effect runs. Schema failures re-prompt Claude with the validator
  errors and the last raw output up to the configured retry budget;
  on exhaustion the task lands in `failed` with `failure_kind="schema"`
  and `failure_detail` carrying the errors, attempt count, and a
  truncated raw snippet. The admin task detail view renders these
  inline — no log dive required. Retry lifecycle events
  (`worker_output_compliance.{ok,retry,failed}`) flow through the
  structured log stream ([observability-and-cost-tracking](../../designs/active/observability-and-cost-tracking.md))
  so operators can see which prompts are drifting. Runbook:
  [`worker-schema-failure`](../../runbooks/worker-schema-failure.md).
- **Worker transient-failure retry.** Every role worker (all five —
  PM, Architect, Team Manager, Developer, Reviewer) wraps its
  `claude` subprocess spawn in a classify-and-retry loop. A failure
  classified as transient (Anthropic 429/529, socket reset, read
  timeout, DNS) re-spawns with full-jitter exponential backoff up to
  the configured budget before surfacing. Budget exhaustion writes
  `failure_kind="transient"` with a `failure_detail` carrying the
  canonical `error_kind`, attempt count, per-attempt delays, and a
  truncated `last_stderr`. Success-after-retry populates a separate
  `tasks.transient_retry_history` column (migration 0021) so the
  admin panel can render a yellow "recovered after N transient
  retries" chip without a log dive. Lifecycle events
  (`worker_transient_retry.{attempt,succeeded,exhausted,unknown}`)
  flow through the observability feed. The retry lives inside the
  worker per ADR 0013 — the pre-0027 dispatcher-level wrapper was
  removed on ship. Runbook:
  [`worker-transient-failure`](../../runbooks/worker-transient-failure.md).
- **Concurrent pipelines with per-project fairness.** A process-wide
  `DispatcherQueue` sits in front of `orchestrate_task`: waiters are
  queued per-project and admission rotates round-robin across
  projects with queued work so one tenant can't monopolise the
  global `worker_concurrency` cap. Each project optionally carries a
  soft cap (`projects.worker_concurrency_soft`, migration 0027) that
  yields the project's turn to another waiter once hit — soft
  semantics, no ceiling on idle-fleet workloads. Queue depth is
  exposed per-project (`GET /v1/projects/{id}/ops/queue-depth`) and
  fleet-wide (`GET /v1/_admin/ops/queue-depth`); the admin panel
  renders the per-project Queue strip on the project dashboard and
  the Fleet queue widget on the admin home. Lifecycle events
  (`dispatcher_queue.{enqueued,dequeued,starved_yield}`) flow through
  the structured-log feed with wait-time timing. Runbook:
  [`concurrency-overflow`](../../runbooks/concurrency-overflow.md).
- **Ship-gate close-cycle backstop.** When every developer task for a
  run's spec reaches `accepted`, `on_all_dev_tasks_accepted` consults
  the Knowledge API's orphan-WIP query before promoting the run to
  `pm_acceptance`. A non-empty result stamps `wips_pending_merge` +
  `blocked_since` on the pipeline run, publishes a structured
  `pipeline_run.close_cycle_blocked` event, and (behind
  `settings.ship_draft_dispatch_enabled`) auto-dispatches a
  `knowledge-ship-draft` architect task seeded with the orphaned WIP
  body so the admin ship-gate panel opens pre-populated. Ship-draft
  dispatch is idempotent on the architect-task side: a second call for
  the same spec reuses the queued draft rather than creating a
  duplicate. Fails open on GitHub errors — an API outage never traps
  a cycle. ADR 0015 keeps the gate inside the Coder pipeline rather
  than GitHub branch protection.
- **Pipeline-run dashboard signals.** Every `pipeline_runs` row
  carries two timing columns (migration 0028): `step_started_at`
  resets on every step transition, and `blocked_since` is set while
  the run sits in a `*_approval` step and cleared on resolution. The
  pair powers the admin Runs list's blocked-longest-first sort and
  the per-run Timeline strip. Per-step duration statistics roll up
  nightly into `pipeline_step_stats` (migration 0029); the median is
  exposed via `GET /v1/projects/{id}/ops/step-stats` and an admin-only
  `POST /v1/_admin/ops/step-stats/recompute`. Two new SSE event types
  (`pipeline_run.changed`, `pipeline_run.gate_blocked`) fire on every
  row mutation so the dashboard can stay live without polling. The
  `RunDetail` page renders an inline Gate card when `blocked_since`
  is set — operators approve, request-changes, or reject a pending
  spec/design without leaving the run view. Runbook:
  [`pipeline-run-blocked`](../../runbooks/pipeline-run-blocked.md).

## Interfaces

- `POST /v1/projects/{id}/tasks` — create; new tasks start at `queued`.
  PM `draft:` prompts auto-create a `pipeline_run`.
- `GET /v1/projects/{id}/tasks?stage=&status=&role=` — list with filters.
- `POST /v1/projects/{id}/tasks/{task_id}/override` — pause / resume /
  retry / skip_to_stage / reject.
- `POST /v1/projects/{id}/tasks/{task_id}/retry` — clone a terminal
  task into a fresh queued one.
- `POST|GET /v1/projects/{id}/tasks/{task_id}/messages` — structured
  worker conversation; SSE `message_created` events.
- `GET /v1/projects/{id}/tasks/{task_id}/stage-runs?stage=&status=&limit=`
  — archived per-dispatch snapshots, oldest-first.
- `POST /v1/projects/{id}/knowledge/{specs|designs}/{id}/approve|reject`
  — gate endpoints; SSE `knowledge_approved` / `knowledge_rejected`.
- `GET /v1/projects/{id}/pipeline-runs` and
  `POST /v1/projects/{id}/pipeline-runs/{id}/override` — end-to-end run
  visibility and pause/resume/cancel.

## Dependencies

- Postgres (`tasks`, `task_messages`, `task_logs`, `pipeline_runs`,
  `knowledge_reviews`) — state of record. Migrations 0010, 0013, 0015,
  0017 own the schema.
- Developer, Reviewer, PM, Architect, Team Manager workers — the stages
  the orchestrator drives.
- Knowledge write API — file moves and registry updates for approvals.
- SSE event bus — real-time admin updates for message and gate events.
- GitHub Contents API — backs the approve flow's file move.

## Evolution

- `0010-task-orchestration-v1` — state machine, fix loop, `/override`,
  stage filter. Migration 0010.
- `0015-worker-communication` — `task_messages`, verdicts, SSE
  `message_created`, fix-context includes recent messages. Migration 0013.
- `0019-task-retry-endpoint` — `/retry`, `original_task_id`, terminal-
  state gate, retry audit log. Migration 0015.
- `0022-spec-design-approval-gates` — `/approve` and `/reject` for specs
  and designs, revision-task spawn, `knowledge_approved|rejected` SSE.
- `0021-pipeline-chaining` — `pipeline_runs`, chain hooks on approvals
  and on all-dev-accepted, PM-draft auto-run, pause/resume/cancel.
  Migration 0017. Proved end-to-end on 2026-04-13.
- `0024` — `GET /tasks/{task_id}/stage-runs` read endpoint over the
  `task_stage_runs` archive (migration 0018). Ordered by `recorded_at`
  ascending; filters on `stage` and `status`; 1–500 limit. No new
  schema.
- `0025` — worker output compliance: per-worker JSON schemas,
  `validate_and_retry` gate in front of dispatcher Phase 4, new
  `tasks.failure_kind` / `failure_detail` / `output_schema_version`
  columns (migration 0020), admin task-detail renders schema failures
  inline. Enforcement behind `worker_output_compliance_enabled`; flag
  default flips to `true` after the 48 h shadow soak confirms healthy
  retry-success rates. ADR 0012 documents the re-prompt-only
  remediation rule.
- `0027` — worker transient-failure retry: `_transient.classify` +
  `run_with_transient_retry` wrap every role worker's claude spawn.
  Migration 0021 adds `tasks.transient_retry_history` (recovered
  runs). Each worker's internal task-deadline signature was updated
  from `exit_code=124 + "claude CLI timed out"` to
  `exit_code=-9 + "coder task deadline exceeded"` so the classifier
  doesn't retry our own deadline hits. Pre-0027 dispatcher-level
  retry removed per ADR 0013.
- `0028` — concurrent pipelines with per-project fairness: a global
  cap (`worker_concurrency`, already live in a pre-0028 sliver) plus
  a `DispatcherQueue` that round-robins admission across projects
  with queued work. Migration 0027 adds the optional soft per-project
  cap. Two new queue-depth endpoints and two admin surfaces
  (per-project Queue strip + Fleet queue widget). The pre-0028
  semaphore-only path is retained for `worker_concurrency <= 0`
  disable-the-cap operation.
- `0044` — write-through enforcement on ship: close-cycle backstop
  in `on_all_dev_tasks_accepted` stamps `wips_pending_merge` +
  `blocked_since` on the pipeline run when
  `/knowledge/wips?shipped=true` returns non-empty; publishes
  `pipeline_run.close_cycle_blocked` SSE; optional
  `knowledge-ship-draft` architect auto-dispatch behind
  `settings.ship_draft_dispatch_enabled` (idempotent on the task
  side). ADR 0015 fixes the gate inside the Coder pipeline rather
  than GitHub branch protection.
- `0026` — pipeline-run dashboard: migrations 0028 + 0029 add
  `pipeline_runs.step_started_at` / `blocked_since` and the
  `pipeline_step_stats` rollup table. New `advance_step(row, step)`
  helper on `PipelineRunRow` centralises the timing-column writes
  across the six existing transition sites. Two new SSE event types
  (`pipeline_run.changed`, `pipeline_run.gate_blocked`) fire through
  the existing subscriber feed. Admin surfaces: inline Gate card on
  RunDetail + blocked-longest-first sort on the Runs list.

## Links

- Designs: —
- Related components: —
