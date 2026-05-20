---
id: worker-communication
title: Worker Communication
type: design
status: active
owner: ro
created: 2026-04-12
updated: 2026-05-20
last_verified_at: 2026-05-20
summary: Task-state machine, dispatcher protocol, SSE streaming, timeout-stall stamping, and per-task tool-use surfacing.
implements_specs: [task-orchestration]
decided_by: []
related_designs: [system-overview, pm-worker, team-manager-worker, task-lifecycle, self-healing, admin-panel]
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

**`tasks` columns for timeout-stall visibility (spec 0096):**

| Column | Type | Notes |
|---|---|---|
| `timeout_stage` | `VARCHAR(20)` NULL | Pipeline stage at timeout; copied from `tasks.stage` on `status=timed_out` write |
| `timeout_total_elapsed_s` | `INTEGER` NULL | `ceil((now - started_at).total_seconds())`; `NULL` when `started_at` is `None`; clamped to ≥0 on clock skew |
| `timeout_stage_elapsed_s` | `INTEGER` NULL | Seconds inside the final stage at timeout (separate from total elapsed) |

`tasks/service.py::_stamp_timeout_fields(row, now)` reads `row.stage`
and `row.started_at` and writes all three fields onto the ORM row
before any `status=timed_out` commit — atomic with the status write,
no partial-stamp window. Called from both the dispatcher lease
expiry (`dispatcher.py::_expire_leased_tasks`) and the zombie
reaper in `self_heal.py`. Re-timing-out an already-`timed_out`
task overwrites all three fields.

**`task_tool_uses` table (spec 0099 backing surface).**
Recorded worker `Bash` invocations are written by the dispatcher on
task completion. The `GET .../tasks/{task_id}/tool-uses` endpoint
returns the rows paginated, project-scoped (404 on cross-project
fetch — asserted by integration test). The admin panel's
knowledge-reads panel filters client-side for the
`repos/{org}/{repo}/contents/` path shape; no backend filtering.
A subcount on `task_tool_uses` populates `TaskRead.knowledge_read_count`
in the task-list query so the pipeline row badge needs no extra
round-trip.

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
- **Timeout fields are atomic with `status=timed_out`.**
  `_stamp_timeout_fields` runs in the same session as the status
  write; partial-stamp states are unreachable. Pre-spec-0096 rows
  keep `NULL` for all three timeout columns; the UI treats `NULL`
  as "unknown stage".
- **Tool-use rows are project-scoped.** Cross-project fetches return
  404; tenant isolation is asserted by integration test (per spec
  0099 AC).

## Interfaces

- `POST` / `GET` message endpoints above.
- SSE `PipelineEvent { event_type: "message_created", ... }`.
- Admin panel message-thread component on the task detail page.
- `GET /v1/projects/{pid}/tasks/{tid}` response gains
  `timeout_stage` (string | null), `timeout_total_elapsed_s`
  (int | null), `timeout_stage_elapsed_s` (int | null), and
  `knowledge_read_count` (int | null) — only the timeout fields
  are populated on `status=timed_out` rows.
- `GET /v1/projects/{pid}/tasks/{tid}/tool-uses` — paginated
  `task_tool_uses` rows; project-scoped; 404 on cross-project
  fetch. Primary consumer: `coder-admin` knowledge-reads panel.

## Evolution

- 2026-04 — Initial ship (spec 0015): `task_messages` table,
  endpoints, orchestrator integration, admin thread UI. Replaced the
  pre-0015 single `review_verdict` poll.
- 2026-04-19 — observability + control week: stage-runs read endpoint,
  worker output compliance gate, transient-failure retry,
  per-project fairness queue, pipeline-run dashboard, in-panel PR
  diff viewer (specs 0024–0028, 0033, 0034).
- 2026-04-19 — audit-log wiring for task / plan / pipeline-run
  mutations through `record_audit_event` (spec 0037), atomic with
  the underlying transaction.
- 2026-05-20 — Timeout-stall stamps (spec 0096): `timeout_stage`,
  `timeout_total_elapsed_s`, and `timeout_stage_elapsed_s` written
  atomically with `status=timed_out` from both the dispatcher and
  the zombie reaper.
- 2026-05-20 — Tool-use endpoint (spec 0099):
  `GET .../tasks/{tid}/tool-uses` exposes the existing
  `task_tool_uses` rows for the admin knowledge-reads panel;
  `knowledge_read_count` populated via subcount on the task-list
  query. ADR 0041 documents the derive-at-query-time choice.

## Links

- Specs: [task-orchestration](../../../product-specs/active/pipeline/task-orchestration.md)
- Designs: system-overview, team-manager-worker, pm-worker,
  task-lifecycle, self-healing, admin-panel
- ADRs: [0041](../../../adrs/0041-derive-knowledge-pulls-at-query-time-from-task-tool-uses.md)
- Services: `coder-core`, `coder-admin`
