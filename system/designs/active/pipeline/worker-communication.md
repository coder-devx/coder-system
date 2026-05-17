---
id: worker-communication
title: Worker Communication
type: design
status: active
owner: ro
created: 2026-04-12
updated: 2026-04-19
last_verified_at: 2026-04-19
summary: Task-state machine, dispatcher protocol, and SSE streaming.
implements_specs: [task-orchestration]
decided_by: []
related_designs: [system-overview, pm-worker, team-manager-worker]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin]
parent: pipeline-operations
---

# Worker Communication

## What it is

Workers talk to each other — and to the human — through structured
**task messages**. A message is a row on a task thread carrying a
sender role, optional target role, message type, and body. Messages
make inter-worker conversation explicit, auditable, and visible in the
admin panel. The orchestrator reads the latest verdict message to
drive stage transitions, replacing the old opaque `review_verdict`
column on the task row.

## Architecture

```mermaid
flowchart TB
  dev[developer] -->|POST message| api[coder-core<br/>POST /tasks/{id}/messages]
  rev[reviewer] -->|POST message| api
  admin_user[admin override] -->|POST message| api
  api --> db[(task_messages)]
  api -->|SSE message_created| panel[admin panel thread]
  orch[orchestrator] -->|read latest verdict| db
  orch -->|prepend to fix_context| dispatcher
  dispatcher --> dev
```

### Parts

**`task_messages` table:**

| Column | Type | Notes |
|---|---|---|
| `id` | `VARCHAR(36)` PK | UUID |
| `task_id` | `VARCHAR(36)` FK → tasks | Task this message belongs to |
| `project_id` | `VARCHAR(40)` FK → projects | Denormalized |
| `from_role` | `VARCHAR(40)` | `developer`, `reviewer`, `admin`, `orchestrator`, … |
| `to_role` | `VARCHAR(40)` NULL | NULL = broadcast |
| `msg_type` | `VARCHAR(20)` | `feedback`, `question`, `decision`, `override` |
| `verdict` | `VARCHAR(20)` NULL | `approve`, `request_changes`, `reject` (decisions only) |
| `body` | `TEXT` | Free-form |
| `created_at` | `TIMESTAMPTZ` | Immutable |

Index: `ix_task_messages_task_id` on `(task_id, created_at)`.

**`tasks` table additions for structured failures and recovered-retry history:**

| Column | Migration | Type | Notes |
|---|---|---|---|
| `failure_kind` | 0020 | `VARCHAR(20)` NULL | `schema` \| `transient` \| other — NULL on success |
| `failure_detail` | 0020 | `JSONB` NULL | Validator errors + raw snippet (schema), or `{error_kind, attempts, delays_ms, last_stderr}` (transient) |
| `output_schema_version` | 0020 | `VARCHAR(20)` NULL | Schema version the worker validated against; pinned per task |
| `transient_retry_history` | 0021 | `TEXT` NULL | JSON `{attempts, delays_ms, error_kind}` — populated only when the task **recovered** from one or more transient retries. NULL on first-attempt success and on budget-exhausted transients (those use `failure_detail`). |

Index: `ix_tasks_failure_kind_created_at` on `(failure_kind, created_at)`
for admin queries. Schema columns populated by the structured-output
workers (PM, Architect, TM) via
`workers/_compliance.py::validate_and_retry`. Transient columns
populated by all five role workers via
`workers/_transient_retry.py::run_with_transient_retry`.

Endpoints:

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/projects/{id}/tasks/{task_id}/messages` | Post a message |
| `GET` | `/v1/projects/{id}/tasks/{task_id}/messages` | List messages chronologically |

### Data flow

1. A worker (e.g. reviewer) POSTs a message with `verdict` and
   `body`. The row is persisted; an SSE `message_created` event
   fires carrying `{task_id, from_role, msg_type}`.
2. The orchestrator reads the latest verdict message on the task
   thread to decide the next stage:
   - `approve` → ACCEPTED
   - `request_changes` → FIXING (prepend message body to `fix_context`)
   - `reject` → REJECTED
3. When the dispatcher runs the next worker attempt, it appends the
   latest thread messages to the prompt so the developer sees
   reviewer feedback inline.
4. Human overrides posted via the override endpoint are recorded as
   messages with `msg_type=override`.
5. The admin panel's task detail page renders the full thread.

### Invariants

- Messages are immutable once written.
- The thread is the authoritative inter-worker conversation — the
  orchestrator no longer reads the legacy `review_verdict` column
  for new tasks (kept only for backward compatibility).
- Every decision (accept / fix / reject) that moves a task stage is
  traceable to a verdict message with an author.
- `project_id` denormalization keeps cross-tenant isolation cheap at
  query time.

## Interfaces

- `POST` / `GET` message endpoints above.
- SSE `PipelineEvent { event_type: "message_created", ... }`.
- Admin panel message-thread component on the task detail page.

## Evolution

- Pre-0015 — reviewer wrote a single `review_verdict` column; the
  orchestrator polled it. Opaque and un-auditable.
- `0008-worker-communication` (spec 0015) — introduced the
  `task_messages` table, the endpoints, orchestrator integration,
  and the admin thread UI.
- `0024` — added the
  `GET /v1/projects/{id}/tasks/{task_id}/stage-runs` read endpoint
  (`api/task_stage_runs.py`) over the existing `task_stage_runs`
  archive (migration 0018). Ordered by `recorded_at` ascending;
  `stage` / `status` / `limit` filters; no schema change.
- `0025` — worker output compliance: migration 0020 adds
  `tasks.failure_kind`, `failure_detail`, `output_schema_version`;
  the task-detail admin panel renders schema-failed tasks inline
  (validator errors + raw snippet up to 4 KB) via the
  `failure_kind="schema"` branch. `worker_output_compliance.*`
  structured log events flow through the existing observability
  feed; no new counter table per design 0018.
- `0027` — worker transient-failure retry: migration 0021 adds
  `tasks.transient_retry_history` for recovered runs. The admin
  task-detail grows a yellow "recovered after N transient retries"
  chip (recovered) and a yellow panel sibling to 0025's schema panel
  (budget-exhausted). `worker_transient_retry.*` events ride the
  same structured log feed. The pre-0027 dispatcher-level retry was
  removed on ship per ADR 0013.
- `0028` — concurrent pipelines with per-project fairness:
  `workers/_dispatcher_queue.py` sits in front of the existing
  `orchestrate_task` concurrency gate. Migration 0027 adds
  `projects.worker_concurrency_soft` for the optional soft cap;
  `dispatcher_queue.{enqueued,dequeued,starved_yield}` events
  ride the structured-log feed. Two new queue-depth endpoints
  (`api/ops.py`) power the admin panel's per-project Queue strip
  and Fleet queue widget.
- `0026` — pipeline-run dashboard: migration 0028 adds
  `pipeline_runs.step_started_at` and `blocked_since` (the second
  indexed for the blocked-longest-first sort); migration 0029 adds
  the `pipeline_step_stats` rollup table. The
  `advance_step(row, step)` helper on
  `domain/pipeline_run.py` centralises the timing-column writes
  across the six existing transition sites. Two new SSE event types
  (`pipeline_run.changed`, `pipeline_run.gate_blocked`) fire through
  the existing `events.py` publisher so the admin dashboard can stay
  live without polling. `api/ops.py` gains two endpoints for the
  step-stats rollup and its admin-triggered recompute.
- `0033` — live pipeline-run timeline: new
  `GET /v1/projects/{id}/pipeline-runs/{run_id}/timeline` in
  `api/pipeline_runs.py` reconstructs per-run step timings from the
  existing `task_stage_runs` archive, joined via the run's four
  per-role task ids, enriched with `pipeline_step_stats` median/p75
  per lane. A synthetic striped "blocked" bar is appended when
  `pipeline_runs.blocked_since` is non-null and the run is in the
  current lane's step. No new tables, no new events — the admin
  `RunTimeline.tsx` subscribes to the same `pipeline_run.changed`
  feed from 0026 and refetches the payload on change. Message-heavy
  events (`message_created`, `task_updated`, `stage_changed`) are
  filtered out of the refetch trigger.
- `0034` — in-panel PR diff viewer: new
  `GET /v1/projects/{id}/tasks/{task_id}/pr` in `api/tasks.py` parses
  `tasks.pr_url` via `parse_pr_url` and fans out two concurrent
  GitHub API calls — `GitHubClient.fetch_pr` (metadata) and
  `fetch_pr_diff` (unified-diff text, `Accept: application/vnd.github.diff`)
  — then stitches the reviewer's existing `review_verdict` /
  `review_body` into a single envelope. Tasks without a PR return
  `{pr_url: null}` instead of 404. Reuses the same installation-token
  path the Knowledge API depends on; no new auth surface. Admin
  `PrViewer.tsx` lazy-loads on toggle and renders with a custom
  Tailwind-only diff renderer.
- `0037` — audit log wiring for task mutations:
  `tasks.retry` / `override` / `merge`, `task_plans.approve` /
  `reject`, and `pipeline_runs.override` each call
  `record_audit_event(...)` inside their existing transaction.
  Worker-initiated writes (service-account callers) pass the task's
  `pipeline_run_id` as `correlation_id` so a run's mutations cluster
  on one ID without an inbound HTTP correlation header. No schema
  change on the task side — actor/before/after land on
  `audit_events` via the new audit-log component.

## Links

- Specs: [`0015`](../../product-specs/wip/0015-worker-communication.md)
- Designs: system-overview, team-manager-worker, pm-worker
- Services: `coder-core`, `coder-admin`
