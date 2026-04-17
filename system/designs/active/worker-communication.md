---
id: worker-communication
title: Worker Communication
type: design
status: active
owner: ro
created: 2026-04-12
updated: 2026-04-15
implements_specs: [task-orchestration]
decided_by: []
related_designs: [system-overview, pm-worker, team-manager-worker]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin]
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

**`tasks` table additions for schema failures (migration 0020):**

| Column | Type | Notes |
|---|---|---|
| `failure_kind` | `VARCHAR(20)` NULL | `schema` \| `transient` \| other — NULL on success |
| `failure_detail` | `JSONB` NULL | Validator errors, truncated raw output, attempt count, classifier kind |
| `output_schema_version` | `VARCHAR(20)` NULL | Schema version the worker validated against; pinned per task |

Index: `ix_tasks_failure_kind_created_at` on `(failure_kind, created_at)` for admin queries. Columns populated by the
structured-output workers (PM, Architect, TM) via
`workers/_compliance.py::validate_and_retry`.

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

## Links

- Specs: [`0015`](../../product-specs/wip/0015-worker-communication.md)
- Designs: system-overview, team-manager-worker, pm-worker
- Services: `coder-core`, `coder-admin`
