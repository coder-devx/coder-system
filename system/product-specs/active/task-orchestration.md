---
id: task-orchestration
title: Task orchestration
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: [worker-communication]
related_specs: [audit-log]
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
- **Shared per-run context block.** At pipeline-run creation the
  orchestrator materialises a project context block (system-prompt
  header + project brief + AGENTS.md, capped at 64 KiB, fail-open on
  GitHub outages) into `pipeline_run_contexts` (migration 0032) and
  back-links every chain-dispatched task to its run via
  `tasks.pipeline_run_id` (migration 0033) — PM draft, architect, team
  manager, developer fan-out, reviewer retries, and PM acceptance.
  The dispatcher loads the block at task start, stamps it on
  `WorkerInput.project_context_block` + `_block_hash`, and logs the
  hash so sibling tasks in one run can be audited for byte-identity
  (the invariant the prompt cache rides on). As of 2026-04-19
  `PROMPT_CACHING_ENABLED=true` fleet-wide, so each role worker's
  system-prompt assembler prepends the block, driving the claude
  CLI's internal `cache_control` markers. Per-project
  `projects.prompt_caching_enabled` (migration 0034) tri-state still
  lets an operator opt a project out. Design
  [0029](../../designs/wip/0029-prompt-caching.md).
- **Model tier routing.** `resolve_tier_model` in the dispatcher
  picks a per-role low-tier model (`worker_model_low_tier_{role}`
  config) when the effective tier-routing flag is on. Resolution
  order: explicit `tasks.model_override` wins; `projects.pin_top_tier`
  True pins to role default; `pin_top_tier=False` forces policy
  regardless of the fleet flag; NULL falls through to
  `settings.tier_routing_enabled`. The dispatcher stamps the resolved
  model on `WorkerInput.model_override`; runners use their existing
  fallback. `tasks.model` records what actually ran. As of 2026-04-19
  the fleet flag is still False; `coder` runs as the first canary
  with `pin_top_tier=false`, routing reviewer tasks to
  `claude-haiku-4-5-20251001`. Migrations 0036 + 0037. Design
  [0030](../../designs/wip/0030-model-tier-routing.md).
- **Per-project token budgets.** Dispatcher pre-dispatch gate fails
  tasks with `failure_kind="budget"` when the project's calendar-month
  spend exceeds the resolved hard cap.
  `projects.budget_{soft,hard}_tokens` (migration 0035) override the
  `settings.project_token_{soft,hard}_limit` fleet defaults via
  `coder_core.api.projects.resolve_budget_limits`. `PATCH
  /v1/projects/{id}` with the project's API key sets the overrides;
  `GET /v1/projects/{id}/budget` returns the current-period rollup.
  Soft-breach Slack alert deduplicates per calendar month via the
  yyyymm suffix on `alert_type`. No project currently sets a cap;
  machinery is latent until ops configures them. Design
  [0031](../../designs/wip/0031-token-budgets.md).
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
- **Spec-lifecycle coordinator.** A per-spec lifecycle state machine
  generalises ADR 0015's close-cycle backstop one level up. The
  `spec_runs` table (migration 0061) tracks each WIP spec as it moves
  `accepted → designing → design_landed → planning → plan_pending →
  implementing → ship_pending → shipped` (plus `deprecated` and
  `paused`). PM-accept Phase 4 calls `spec_run_service.start_run` to
  insert the row in `accepted`. A new Cloud Run Job
  `coder-core-spec-coord-tick` runs `coder_core.spec_runs.coordinator.tick`
  every 60 s, claims active runs with `FOR UPDATE SKIP LOCKED`, and
  for each one probes the next transition: `accepted → designing` via
  `dispatch_architect` (creates a `role=architect` task with
  `prompt: design: <wip>`), `designing → planning` via
  `dispatch_team_manager` (creates a `role=team-manager` decompose task)
  when the architect's task lands `succeeded`. Both dispatchers are
  idempotent — an existing non-terminal task for the WIP causes the
  coordinator to reattach with `trigger="manual_override"` rather than
  duplicate-dispatch. Service module `coder_core.spec_runs.service`
  is the only writer of `spec_runs.state`; concurrent ticks observe
  the already-advanced row via `SELECT FOR UPDATE` and become no-ops.
  Operators read state via `GET /v1/projects/{id}/spec-runs[?state=]`
  (list + filter) and `/spec-runs/{wip_spec_id}` (detail with full
  `spec_run.transitioned` audit history); pause/resume via
  `POST .../{wip_spec_id}/{pause,resume}`. The admin Specs page
  (`/projects/:id/specs`, behind `VITE_SPEC_COORDINATOR_ENABLED`)
  renders the fleet view with per-row pause/resume buttons. Three
  audit actions — `spec_run.transitioned`, `spec_run.paused`,
  `spec_run.resumed` — let operators reconstruct any spec's lifecycle
  from the audit log alone. Later-state probes (`planning →
  plan_pending`, `plan_pending → implementing`, `implementing →
  ship_pending`) and circuit breakers (cost cap, retry cap,
  stuck-stage) are follow-up. ADR 0015 still constrains
  scope: human approval gates remain at PM-accept, plan-approve, and
  ship-merge; the coordinator only auto-dispatches at the spawn
  points between them.
- **Confidence-scored auto-approval.** On Phase 4 write for PM-draft,
  Architect, and Team Manager artifacts,
  `evaluate_auto_approval(artifact, gate_kind, project_id)` checks four
  predicates before deciding whether to bypass the human-approval gate:
  (1) project opt-in for the gate kind is `true`
  (`projects.auto_approve_{spec,design,plan}_enabled`); (2) worker
  `self_confidence.score` ≥ the fleet threshold for this gate kind
  (defaults: spec 85, design 90, plan 80 via
  `settings.auto_approve_threshold_{spec,design,plan}` env vars);
  (3) project's historical approval rate on this gate kind ≥ 95% over
  the last N=20 `audit_events.action='knowledge.approve'` rows for the
  project + gate kind (strictly < 5 prior approvals = not-yet-eligible);
  (4) `risk_flags` array is empty — both worker-reported and
  statically-computed from the artifact body (`migration_required`
  triggered by migration filename presence, `external_dependency_added`
  by dependency-manifest delta, `large_blast_radius` by plan task count
  > 5 or > 3 services touched). All four must hold; any failure returns
  `Manual(reason)` and the existing human-approval flow runs unchanged.
  `EligibleForAuto` writes an `auto_approvals` row with
  `status='pending'` (migration 0062), publishes `auto_approval_pending`
  SSE, and withholds `knowledge_approved`. A 1-minute Cloud Scheduler
  Job (`coder-core-auto-approve-tick`) finds expired `pending` rows,
  transitions them to `applied`, publishes `knowledge_approved`, and
  runs the same chain hook as a manual approval — idempotent on
  already-`applied` rows. Two break-glass endpoints on the
  `auto_approvals` row: `POST .../auto-approvals/{id}/undo` (during
  `pending`) transitions to `undone`, publishes `knowledge_rejected`
  with `reason="auto_approval_undone"`, and spawns a revision task
  seeded with the operator's optional `undone_reason` enum
  (`score_below_threshold`, `risk_flag_present`,
  `historical_rate_below_95`, `insufficient_history`) plus free-text;
  undo after `applied` returns 409. `POST
  .../auto-approvals/{id}/accept-now` finalises immediately (same shape
  as tick). Both endpoints and the tick acquire `SELECT FOR UPDATE` on
  the row to prevent a concurrent-finalise race. Per-project tri-state
  opt-in columns `auto_approve_{spec,design,plan}_enabled` (migration
  0062) default `NULL` (inherit fleet flag `AUTO_APPROVE_ENABLED`,
  default `false`). Staged rollout: Stage 1 schema-only (workers emit
  `self_confidence` block; evaluator not wired); Stage 2 shadow
  (evaluator runs on every Phase 4 write, logs outcome, does not
  publish SSE); Stage 3 per-gate threshold flip after shadow data
  reviewed.

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
- `GET /v1/projects/{id}/pipeline-runs/{run_id}/timeline` — per-run
  swim-lane payload: one `TimelineLane` per pipeline step with bars
  reassembled from `task_stage_runs` for the run's four per-role task
  ids, plus `pipeline_step_stats` median/p75 per lane and a synthetic
  striped "blocked" bar when `blocked_since` is set. Powers the
  admin-panel `RunTimeline` component; no new storage.
- `GET /v1/projects/{id}/tasks/{task_id}/pr` — returns PR metadata +
  unified diff (two concurrent GitHubClient calls behind
  `parse_pr_url`) plus the task row's existing `review_verdict` /
  `review_body`. Returns `{pr_url: null}` when the task hasn't pushed
  a PR yet; tenant isolation mirrors `GET /tasks/{id}`. Powers the
  admin panel's inline `PrViewer`.
- `POST /v1/projects/{id}/auto-approvals/{approval_id}/undo` — reverts
  a `pending` auto-approval to `undone`; publishes `knowledge_rejected`;
  spawns a revision task; returns 409 when already `applied`.
- `POST /v1/projects/{id}/auto-approvals/{approval_id}/accept-now` —
  finalises a `pending` auto-approval immediately (same shape as tick
  finalisation); publishes `knowledge_approved` and runs chain hook.

## Dependencies

- Postgres (`tasks`, `task_messages`, `task_logs`, `pipeline_runs`,
  `knowledge_reviews`, `auto_approvals`) — state of record. Migrations
  0010, 0013, 0015, 0017, 0062 own the schema.
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
- `0029` — prompt caching & shared context reuse: migration 0032 adds
  `pipeline_run_contexts` (one row per run, carrying the materialised
  block + sha256 hash), migration 0033 adds `tasks.pipeline_run_id`,
  migration 0034 adds `projects.prompt_caching_enabled` per-project
  override. `coder_core.workers.context.build_project_context`
  composes the block from AGENTS.md; `apply_cache_prefix` prepends it
  to every role worker's system prompt when the effective flag is on.
  The dispatcher's block-load path emits an audit log with
  `block_hash` so sibling byte-identity is grep-able.
  `PROMPT_CACHING_ENABLED=true` on revision `coder-core-00115-vhp`
  (2026-04-19).
- `0030` — model tier routing: migrations 0036/0037 add
  `projects.pin_top_tier` + `tasks.model_override`.
  `resolve_tier_model` in the dispatcher stamps
  `WorkerInput.model_override` so runners hit the picked model
  without changing their own code path. `/metrics` gains `by_tier`.
  `coder` canary runs with `pin_top_tier=false`; fleet
  `tier_routing_enabled` still off.
- `0031` — per-project token budgets: migration 0035 adds
  `projects.budget_{soft,hard}_tokens`. Dispatcher hard-gate +
  soft-breach Slack alert + PATCH API all via
  `resolve_budget_limits`. No project configured yet.
- `0032` — cost regression alerts: migration 0038 adds
  `regression_events`. Nightly cron detects, persists, dedups on
  `(role, metric, day_utc)`. Acknowledge flow
  (`POST /v1/_admin/regression/events/{id}/acknowledge`) suppresses
  repeat fires. `REGRESSION_ALERTS_ENABLED=true` (2026-04-19).
- `0033` — live pipeline-run timeline: new
  `GET /v1/projects/{id}/pipeline-runs/{run_id}/timeline` endpoint
  reconstructs per-run step timings from existing `task_stage_runs`
  joined via the run's four per-role task ids; `pipeline_step_stats`
  supplies per-lane median/p75. No new tables, no new SSE events — the
  admin `RunTimeline.tsx` refetches on the existing
  `pipeline_run.changed` stream. Empty lanes are emitted for
  not-yet-started steps so the grid is stable. Rollout flag lives on
  the frontend (`VITE_RUN_TIMELINE_ENABLED`, default on).
- `0034` — in-panel PR diff viewer: new
  `GET /v1/projects/{id}/tasks/{task_id}/pr` endpoint in
  `api/tasks.py` fans out `GitHubClient.fetch_pr` +
  `fetch_pr_diff` via `asyncio.gather`, stitches the reviewer's
  existing `review_verdict` / `review_body` into a single payload.
  `parse_pr_url` lives next to the client and rejects malformed URLs
  with a typed error. No new tables, no GitHub writes — view-only.
  Admin `PrViewer.tsx` renders the payload; behind
  `VITE_PR_VIEWER_ENABLED` (default on).
- `0037` — audit log wiring: `tasks.retry`, `tasks.override`,
  `tasks.merge`, `task_plans.approve` / `reject`, and
  `pipeline_runs.override` each grow a `record_audit_event(...)`
  call inside the handler's existing transaction. Handlers add
  `Annotated[str, Depends(get_correlation_id)]` to pick up the
  request's correlation ID (worker-initiated writes reuse
  `pipeline_run_id`). Mutation + audit row are atomic — a rollback
  on the outer transaction rolls both back. Gated on
  `CODER_AUDIT_LOG_ENABLED` (default on); short-circuit when off.
  See [audit-log](./audit-log.md).
- `0041` — escalation watcher observation surface (shipped
  2026-04-22): the 1-minute escalation watcher reads `pipeline_runs`
  (`blocked_since`, `started_at`, `step`), `tasks` (`status`,
  `updated_at`), `task_messages`, and `DispatcherQueue.depth(project)`
  to detect stall / failure-streak / SLA-breach conditions. Queued
  tasks are explicitly excluded from stall detection so
  DispatcherQueue blocking from 0028 doesn't misfire. See
  [escalations](./escalations.md).
- `0042` — self-healing watchdog (shipped 2026-04-22): the 5-minute
  watchdog uses the same `tasks` + `pipeline_runs` +
  `DispatcherQueue` read surface as 0041, plus the existing
  override path (`launch_re_enqueue` → `_orchestrate_safe`) as the
  idempotent remediation seam for the `stuck_queued` pattern. No
  new writes to orchestration tables; the watchdog's side effects
  land in `self_heal_attempts` and `audit_events`. See
  [self-healing](./self-healing.md).
- `0055` — `GH_TOKEN` resolved at dispatch for all roles
  (shipped 2026-04-28, [coder-core#41](https://github.com/coder-devx/coder-core/pull/41)).
  Workspace-bearing roles (developer, reviewer) keep using
  `workspace.github_token`; non-workspace roles (architect, TM,
  PM) get a fresh installation token minted against the project's
  knowledge repo via `tokens.get_token_for_repo(github_org,
  knowledge_repo)`, passed through `WorkerInput.github_token`.
  Each role worker calls the shared
  `_github_env.apply_github_token_env` helper to populate
  `GH_TOKEN` in the `claude` subprocess env. Closes the
  manual-dispatch failure mode where architect / TM / PM tasks
  exited with `gh is unauthenticated`. Token-mint failures log a
  warning and leave the env untouched (graceful for local-dev
  paths without a GitHub App). Realised pain: architect task
  `62e0c95e` (2026-04-27).
- `0068` — spec-lifecycle coordinator (shipped 2026-05-04): generalises
  ADR 0015's close-cycle backstop into a per-spec state machine.
  Migration 0061 adds `spec_runs(id, project_id, wip_spec_id, state,
  current_task_id, paused_reason, cost_*_tokens, stage_retry_counts,
  created_at, updated_at)` with unique `(project_id, wip_spec_id)`.
  Service module `coder_core.spec_runs.service` owns all state
  mutations (`start_run`, `advance`, `pause`, `resume`, `record_cost`,
  `bump_retry`); audit constants `spec_run.{transitioned,paused,resumed}`
  let operators reconstruct any run's full lifecycle. Coordinator
  module `coder_core.spec_runs.coordinator.tick` claims active runs
  with `FOR UPDATE SKIP LOCKED` and dispatches the next role's task
  at each transition: `dispatch_architect` on `accepted → designing`,
  `dispatch_team_manager` on `designing → planning` (gated on the
  architect task having reached `succeeded`). Both dispatchers are
  idempotent on the existing-non-terminal-task check, so a manual
  spawn before the coordinator runs is reattached with
  `trigger="manual_override"` rather than duplicated. PM-accept
  Phase 4 in `workers/dispatcher.py` now calls `start_run` on the
  `all_pass=True` branch (fail-open on DB hiccups so accept never
  blocks). REST API `coder_core/api/spec_runs.py` exposes
  `GET /v1/projects/{id}/spec-runs[?state=]`,
  `GET .../spec-runs/{wip_spec_id}` (detail with transition history),
  `POST .../{wip_spec_id}/{pause,resume}`. Admin
  `coder-admin/src/pages/Specs.tsx` (behind
  `VITE_SPEC_COORDINATOR_ENABLED`) renders the fleet view with
  per-row pause/resume actions gated to admin scope. Later-state
  probes (`planning → plan_pending` via task_plans existence,
  `plan_pending → implementing` via plan-approve audit,
  `implementing → ship_pending` via close-cycle backstop) and
  circuit breakers (cost cap, per-stage retry cap, stuck-stage)
  are follow-up; the Cloud Run Job `coder-core-spec-coord-tick`
  schedule lands as part of that follow-up too.
- `0064` — schema-gate recovery (shipped 2026-05-04): the dispatcher
  now persists the full untruncated last-attempt raw output on
  `tasks.raw_output_held` (TEXT, migration 0059) when the
  compliance gate exhausts its retry budget. New endpoint
  `POST /v1/projects/{id}/tasks/{task_id}/gate-replay` accepts
  `{"raw_output": "..."}`: re-runs the task's role-specific schema
  validator in a single pass (no re-prompting — operator path), and on
  pass stores the parsed payload as `tasks.result`, transitions the
  row to `status='succeeded'` (clearing failure_kind / failure_detail
  / error and flipping `stage` from `stuck` back to `accepted`),
  and emits `schema_replay.{attempted,passed}` audit rows; on fail
  returns `422 {errors: [...]}` with the validator messages and emits
  `schema_replay.{attempted,failed}`. Admin TaskDetail renders the
  held output read-only and exposes a "Replay gate" button that opens
  an editable textarea pre-populated with it; submit posts back to the
  endpoint and the panel unmounts on pass via parent re-fetch.
  Three new audit actions — `schema_replay.attempted`,
  `schema_replay.passed`, `schema_replay.failed` — give operators the
  full replay history.
- `0040` — confidence-scored auto-approval (shipped 2026-05-06):
  `auto_approvals` table + per-project opt-in columns
  `auto_approve_{spec,design,plan}_enabled` (migration 0062).
  `evaluate_auto_approval` runs on Phase 4 write for PM-draft,
  Architect, and TM outputs — four-predicate check (opt-in, score ≥
  fleet threshold, historical approval rate ≥ 95% over last N=20
  rows, empty risk flags after static ORing with worker self-report).
  `coder-core-auto-approve-tick` (1-minute Cloud Run Job) transitions
  expired `pending` rows to `applied` and fires the chain hook.
  Undo and accept-now break-glass endpoints, both guarded by
  `SELECT FOR UPDATE`. Fleet flag `AUTO_APPROVE_ENABLED` (default
  false); thresholds in `settings.auto_approve_threshold_{spec,design,plan}`
  env vars. See [audit-log](./audit-log.md) for the four new
  `knowledge.auto_approve_*` action strings.

## Links

- Designs: [worker-communication](../../designs/active/worker-communication.md),
  [pipeline-operations](../../designs/active/pipeline-operations.md)
- Related components: [audit-log](./audit-log.md),
  [observability](./observability.md), [escalations](./escalations.md),
  [self-healing](./self-healing.md),
  [developer-worker](./developer-worker.md),
  [reviewer-worker](./reviewer-worker.md), [pm-worker](./pm-worker.md),
  [architect-worker](./architect-worker.md),
  [team-manager-worker](./team-manager-worker.md),
  [knowledge-api](./knowledge-api.md), [admin-panel](./admin-panel.md)
