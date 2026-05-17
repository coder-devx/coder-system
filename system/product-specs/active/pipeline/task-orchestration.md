---
id: task-orchestration
title: Task orchestration
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-17
last_verified_at: 2026-05-17
summary: Task lifecycle, dispatcher, and stage transitions.
served_by_designs: [worker-communication]
related_specs: [admin-panel, architect-worker, audit-log, developer-worker, escalations, knowledge-api, observability, pm-worker, reviewer-worker, self-healing, team-manager-worker]
parent: pipeline-operations
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
the surrounding `/tasks`, `/messages`, `/retry`, `/approve` / `/reject`,
and `/pipeline-runs` endpoints in `coder-core`.

## Capabilities

- **Stage machine + fix loops.** Tasks advance through
  `queued → enriched → executing → testing → reviewing →
  accepted | rejected | failed`. Every transition is logged with
  `task_id`, `from_stage`, `to_stage`, timestamp. On failure the
  orchestrator prepends `fix_context` (error + failing output + recent
  worker messages) to the prompt and retries from `executing`, up to
  3 attempts. The Reviewer's `request_changes` verdict routes the task
  back into the developer fix loop. Every dispatch snapshot lands in
  `task_stage_runs` (queryable via `GET .../tasks/{id}/stage-runs`).

- **Worker output compliance.** PM, Architect, and Team Manager outputs
  are validated against per-worker JSON schemas (`pm_draft`,
  `pm_accept`, `architect`, `team_manager`) before any Phase 4 side
  effect runs. Schema failures re-prompt Claude with the validator
  errors up to the configured retry budget; on exhaustion the task
  lands in `failed` with `failure_kind="schema"` and a `failure_detail`
  block the admin task-detail view renders inline. The schema-replay
  endpoint (`POST .../tasks/{id}/gate-replay`) lets operators submit
  a hand-corrected payload that re-runs validation, transitions the
  row to `succeeded` on pass, and emits `schema_replay.*` audit rows.

- **Transient-failure retry.** Every role worker wraps its `claude`
  subprocess spawn in a classify-and-retry loop. Failures classified as
  transient (Anthropic 429/529, socket reset, read timeout, DNS) re-spawn
  with full-jitter exponential backoff up to budget; budget exhaustion
  writes `failure_kind="transient"`. Success-after-retry populates
  `tasks.transient_retry_history` so the admin chip can render
  "recovered after N transient retries" without a log dive. The retry
  lives in the worker per ADR 0013 — no dispatcher-level wrapper.

- **Human override + retry.** Operators can pause, resume, retry,
  skip to a stage, or reject any task; overrides land in the message
  thread for audit. One-click retry clones a terminal task into a
  fresh queued one preserving `role`, `prompt`, `repo`, and `spec_id`,
  linking back via `original_task_id`; non-terminal tasks are refused
  with `422`.

- **Pipeline chaining + run dashboard.** A `pipeline_run` row tracks an
  end-to-end flow for one spec. Approving a spec auto-creates an
  Architect task; approving a design auto-creates a TM task; all
  developer tasks reaching `accepted` auto-creates a PM acceptance task.
  Two timing columns (`step_started_at`, `blocked_since`) power the
  admin Runs list's blocked-longest-first sort and the per-run timeline.
  Nightly `pipeline_step_stats` rollup feeds per-lane median/p75.
  Two SSE events (`pipeline_run.changed`, `pipeline_run.gate_blocked`)
  drive the live dashboard without polling. Paused runs stop chaining
  until resumed.

- **Concurrent dispatch with per-project fairness.** A process-wide
  `DispatcherQueue` sits in front of `orchestrate_task`: waiters are
  queued per-project and admission rotates round-robin across projects
  with queued work so one tenant can't monopolise the global
  `worker_concurrency` cap. Each project optionally carries a soft cap
  (`projects.worker_concurrency_soft`) that yields the project's turn
  once hit. Queue depth is exposed per-project and fleet-wide; the
  admin panel renders both. `dispatcher_queue.*` lifecycle events flow
  through the observability feed.

- **Shared per-run context + tier routing + budgets.** At pipeline-run
  creation the orchestrator materialises a project context block
  (system-prompt header + project brief + AGENTS.md, capped 64 KiB,
  fail-open on GitHub) into `pipeline_run_contexts` and back-links
  every chain-dispatched task to its run via `tasks.pipeline_run_id`.
  Each role worker's system-prompt assembler prepends the block,
  driving the claude CLI's internal `cache_control` markers
  (`PROMPT_CACHING_ENABLED=true` fleet-wide). `resolve_tier_model`
  picks a per-role low-tier model when the effective tier-routing flag
  is on; explicit `tasks.model_override` wins, then
  `projects.pin_top_tier`, then `settings.tier_routing_enabled`. The
  dispatcher's pre-dispatch budget gate fails tasks with
  `failure_kind="budget"` when the project's calendar-month spend
  exceeds the resolved hard cap from `projects.budget_*_tokens`.

- **Spec-lifecycle coordinator.** A per-spec state machine generalises
  the close-cycle backstop one level up. The `spec_runs` table tracks
  each WIP spec as it moves
  `accepted → designing → design_landed → planning → plan_pending →
  implementing → ship_pending → shipped` (plus `deprecated` and
  `paused`). A `coder-core-spec-coord-tick` Cloud Run Job runs
  `coder_core.spec_runs.coordinator.tick` every 60 s, claims active
  runs with `FOR UPDATE SKIP LOCKED`, and probes the next transition:
  `accepted → designing` via `dispatch_architect` (with `spec_id`
  bound so the design lands at the matching numeric id per
  ADR 0026), `designing → planning` via `dispatch_team_manager` once
  the architect task succeeds. Both dispatchers are idempotent — an
  existing non-terminal task reattaches with `trigger="manual_override"`
  rather than duplicating. Three entry points start a row in
  `accepted`: (1) the admin spec-detail "Start lifecycle" button →
  `POST .../spec-runs` (201 create, 200 idempotent repeat),
  (2) SpecCompose's `auto_start_lifecycle` flag (default true) after
  the PR opens, (3) the PM-draft Phase 4 handler after the spec file
  commits (swallow-on-exception so Phase 4 is not gated on bootstrap
  success), (4) the historical PM-accept `all_pass` path (preserved as
  regression guard). Operators read state via
  `GET .../spec-runs[?state=]` and `.../spec-runs/{wip_spec_id}`;
  pause/resume via `POST .../{wip_spec_id}/{pause,resume}`. Audit
  actions `spec_run.{transitioned,paused,resumed}` let operators
  reconstruct any spec's lifecycle from the audit log alone. Human
  approval gates remain at PM-accept, plan-approve, and ship-merge;
  the coordinator only auto-dispatches at the spawn points between
  them (ADR 0015).

- **Ship-gate close-cycle backstop.** When every developer task for a
  run's spec reaches `accepted`, `on_all_dev_tasks_accepted` consults
  the Knowledge API's orphan-WIP query before promoting the run to
  `pm_acceptance`. A non-empty result stamps `wips_pending_merge` +
  `blocked_since` on the pipeline run, publishes
  `pipeline_run.close_cycle_blocked`, and (behind
  `settings.ship_draft_dispatch_enabled`) auto-dispatches a
  `knowledge-ship-draft` architect task seeded with the orphaned WIP
  body so the admin ship-gate panel opens pre-populated. Idempotent
  on the architect-task side; fails open on GitHub errors so an API
  outage never traps a cycle.

- **Worker dispatch via Cloud Run Job.** Behind per-project
  `worker_via_job_enabled`, `POST .../tasks` creates the row and kicks
  a `coder-core-worker-tick` execution (one per task) instead of an
  in-process subprocess. The Job entry reads `TASK_ID` from env,
  installs the runtime singletons that mirror the FastAPI lifespan
  (`_install_runtime_singletons` / `_teardown_runtime_singletons`),
  runs the role worker, and writes terminal status before exit —
  durable against Cloud Run service scaling and revision rollouts.
  In-process fallback remains when `gcp_project_id` is unset or the
  job-kick errors. Per-project fairness is preserved via the existing
  admission path.

- **Atomic ADR ID reservation.** When an architect task is admitted,
  the dispatcher inserts an `adr_id_reservations` row before writing
  the run-context block; next-free reads use
  `max(max(registry), max(active_reservations.range_end)) + 1`, so
  concurrent admissions never overlap. The architect's run-context
  block gains an "ADR reservation: [XXXX–YYYY]" line. Terminal-state
  hook releases reservations with zero commits and keeps partial-
  commit reservations as history sentinels.

## Interfaces

- `POST /v1/projects/{id}/tasks` — create; new tasks start at `queued`.
  PM `draft:` prompts auto-create a `pipeline_run`. Optional `spec_id`
  binds an architect task to a WIP spec (see [admin-panel](../knowledge/admin-panel.md)).
- `GET /v1/projects/{id}/tasks?stage=&status=&role=` — list with filters.
- `POST .../tasks/{task_id}/override` — pause / resume / retry /
  skip_to_stage / reject.
- `POST .../tasks/{task_id}/retry` — clone a terminal task into a
  fresh queued one.
- `POST|GET .../tasks/{task_id}/messages` — structured worker
  conversation; SSE `message_created` events.
- `GET .../tasks/{task_id}/stage-runs` — archived per-dispatch
  snapshots, oldest-first; filters on `stage` and `status`.
- `GET .../tasks/{task_id}/pr` — PR metadata + unified diff + reviewer
  verdict for the inline PR viewer.
- `POST .../tasks/{task_id}/gate-replay` — operator submits a
  hand-corrected payload; re-runs the role's schema validator and
  unwedges on pass.
- `POST .../knowledge/{specs|designs}/{id}/{approve|reject}` — artifact
  gates; SSE `knowledge_approved` / `knowledge_rejected`.
- `GET .../pipeline-runs` / `POST .../pipeline-runs/{id}/override` —
  end-to-end run visibility + pause/resume/cancel.
- `GET .../pipeline-runs/{run_id}/timeline` — per-run swim-lane
  payload backing the admin `RunTimeline`.
- `GET .../spec-runs[?state=]` / `GET .../spec-runs/{wip_spec_id}` /
  `POST .../spec-runs` (bootstrap) / `POST .../{wip_spec_id}/{pause,resume}`
  — spec-lifecycle coordinator surface.

## Dependencies

- Postgres (`tasks`, `task_messages`, `task_logs`, `pipeline_runs`,
  `knowledge_reviews`, `task_stage_runs`, `spec_runs`,
  `pipeline_run_contexts`, `adr_id_reservations`) — state of record.
- Developer, Reviewer, PM, Architect, Team Manager workers — the
  stages the orchestrator drives.
- [knowledge-api](../knowledge/knowledge-api.md) — file moves and registry
  updates for approvals; orphan-WIP query for the close-cycle
  backstop; atomic `/knowledge/ship`.
- SSE event bus — real-time admin updates for messages, gates, and
  run lifecycle.
- GitHub Contents API — backs the approve flow's file move.

## Evolution

- 2026-04 — v1 state machine, fix loops, messages, retry, approval
  gates, pipeline chaining (specs 0010, 0015, 0019, 0021, 0022).
- 2026-04-19 — observability week: worker compliance gate, prompt
  caching, model tier routing, token budgets, run dashboard, schema
  replay (specs 0025, 0028–0034, 0064).
- 2026-05 — spec-lifecycle coordinator + worker-dispatch durability +
  atomic ADR reservation + auto-bootstrap from PM-draft / SpecCompose
  / admin button (specs 0056, 0068, 0078, 0085).

## Links

- Designs: [worker-communication](../../../designs/active/pipeline/worker-communication.md),
  [pipeline-operations](../../../designs/active/pipeline-operations.md)
- Related components: [audit-log](../tenancy/audit-log.md),
  [observability](./observability.md), [escalations](./escalations.md),
  [self-healing](./self-healing.md),
  [developer-worker](../workers/developer-worker.md),
  [reviewer-worker](../workers/reviewer-worker.md), [pm-worker](../workers/pm-worker.md),
  [architect-worker](../workers/architect-worker.md),
  [team-manager-worker](../workers/team-manager-worker.md),
  [knowledge-api](../knowledge/knowledge-api.md), [admin-panel](../knowledge/admin-panel.md)
