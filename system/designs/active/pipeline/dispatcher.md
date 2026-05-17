---
id: dispatcher
title: Task dispatcher
type: design
status: active
owner: ro
created: '2026-05-17'
updated: '2026-05-17'
last_verified_at: '2026-05-17'
summary: Per-project fair-scheduled task dispatcher; SKIP LOCKED lease + Cloud Run Job execution.
implements_specs:
- pipeline-operations
decided_by: []
related_designs:
- worker-communication
- worker-dispatch-durability
- pipeline-operations
affects_services:
- coder-core
affects_repos:
- coder-core
parent: pipeline-operations
---

# Task dispatcher

## What it is

Bridge between HTTP task creation and worker subprocess execution.
Leases queued rows race-safely, assembles the worker prompt, spawns the
`claude` CLI, records the terminal outcome. A per-project fair queue
sits in front of the global concurrency cap so no project monopolises
worker slots.

## Architecture

```mermaid
sequenceDiagram
  participant API as POST /tasks
  participant Q as DispatcherQueue
  participant DB as Postgres
  participant W as claude CLI
  API->>DB: INSERT task (status=queued)
  Q->>DB: SELECT ... FOR UPDATE SKIP LOCKED
  Q-->>Q: acquire(project_id, role) — fair admit
  Q->>DB: UPDATE status=running
  Q->>W: spawn(args, system_prompt, env)
  W-->>Q: JSON envelope (result + tokens)
  Q->>DB: UPDATE status=succeeded|failed|timed_out
  Q->>Q: release(project_id)
```

### Parts

- `dispatch_task` — single-stage entry; one lease attempt, exits cleanly on lease miss.
- `orchestrate_task` — multi-stage wrapper; loops through pipeline stages until terminal.
- `DispatcherQueue` — in-memory per-project FIFO in front of a process-wide concurrency semaphore; round-robins on release so no project starves.
- `_build_workspace` — assembles `WorkspaceConfig` from project row + selected repo + minted GitHub token.

### Data flow

Caller posts to `/v1/projects/{id}/tasks` → row inserted `queued`.
Dispatcher leases via SKIP LOCKED, fair queue admits, semaphore slot
opens, worker spawns. On exit, JSON envelope parses, outcome persists,
queue releases, next admit triggers.

### Invariants

- Exactly one dispatcher wins each lease (SKIP LOCKED); losers see None and return without error.
- Fair-queue state is per-process; crash recovery relies on the orphan reaper (spec 0042) to mark abandoned rows `timed_out`.
- Project archive is re-checked after the `running` transition; mid-task archive is honoured.
- Legacy tasks with `stage=NULL` are not admitted for new stage transitions.

## Interfaces

| Symbol | Surface |
|---|---|
| `POST /v1/projects/{id}/tasks` | Create task; row enters `queued` |
| `dispatch_task(task_id)` | Single-stage entry |
| `orchestrate_task(task_id)` | Multi-stage stage loop |
| `settings.worker_concurrency` | Process-wide hard limit |
| `projects.worker_concurrency_soft` | Per-project soft cap |

## Where in code

- `src/coder_core/workers/dispatcher.py` — `dispatch_task` (lease → run → record; SKIP LOCKED at top)
- `src/coder_core/workers/_dispatcher_queue.py` — `DispatcherQueue` (per-project fair queue; `acquire` / `release`)
- `src/coder_core/workers/orchestrator.py` — `orchestrate_task` (stage loop)
- `src/coder_core/workers/dispatcher.py` — `_build_workspace` (workspace config assembly)

## Evolution

- Initial in-process dispatcher (spec 0014).
- Per-project fair queue added (spec 0028).
- Cloud Run Jobs migration in flight (design `worker-dispatch-durability`, spec 0056).

## Links

- Specs: pipeline-operations
- Designs: worker-communication, worker-dispatch-durability, pipeline-operations
- Repos: coder-core
