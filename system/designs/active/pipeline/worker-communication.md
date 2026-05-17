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

## Links

- Specs: [`0015`](../../../product-specs/wip/0015-worker-communication.md)
- Designs: system-overview, team-manager-worker, pm-worker
- Services: `coder-core`, `coder-admin`
