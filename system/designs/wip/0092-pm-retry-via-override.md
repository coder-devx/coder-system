---
id: 0092
title: PM retry via override
type: design
status: wip
owner: ro
created: '2026-05-13'
updated: '2026-05-13'
last_verified_at: '2026-05-13'
implements_specs:
- 0092
decided_by: []
related_designs:
- worker-communication
- self-healing
- worker-dispatch-durability
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-admin
parent: pipeline-operations
---

# PM retry via override

## Context

`POST /v1/projects/{pid}/tasks/{id}/override` blanket-rejects non-reject actions when `stage IS NULL` with `409 no_pipeline`. This is correct for pre-pipeline legacy rows but catches three live cases: PM tasks queued by the founder approve handler ([coder-core#236](https://github.com/coder-devx/coder-core/pull/236)); architect and team-manager tasks queued by `POST /spec-runs` before the dispatcher claims them. As of 2026-05-13, five PM tasks have sat at `stage=null` for 12–21 h. The coordinator's rekick scan (`coordinator.py`) also misses them — its Phase 1 filter requires `stage='executing'`, so these tasks fall outside both the operator override path and the automatic recovery path.

## Goals / non-goals

Goals: make `action: retry` succeed on queued `stage=null` tasks whose role is in `_RUNNERS`; widen the coordinator scan to auto-rekick them; enable the admin "Retry" button for these tasks; narrow 409 to surfaceable reasons.

Non-goals: `action: cancel` for stage=null tasks (follow-on spec); assigning stage in the override handler (dispatcher is the single `stage` writer); changing `_PIPELINE_ROLES`.

## Design

```mermaid
sequenceDiagram
    participant Op as Operator
    participant API as /override
    participant DB as Postgres
    participant Job as coder-core-worker

    Op->>API: {action: retry}, stage=null PM task
    API->>DB: load row; role ∈ supported set → ok
    API->>DB: status=QUEUED, fix_attempts=0
    API->>Job: kick_worker_job(task_id)
    API-->>Op: 200 {status: queued, stage: null}
    Job->>DB: SELECT FOR UPDATE SKIP LOCKED
    Job->>DB: status=running, started_at=now
    note over Job: orchestrate_task assigns stage at pickup
```

### Surface 1 — override handler (`src/coder_core/tasks/service.py`)

Replace the blanket `if row.stage is None and action != "reject": raise TaskError("no_pipeline", ...)` with a role-aware guard. For `action="retry"` with `stage=null`:

- `role` not in supported set (`pm`, `architect`, `team-manager`, `developer`, `reviewer`) → 409 `unknown_role`.
- `status` already terminal (`cancelled`) → 409 `invalid_override`.
- Otherwise: fall through to the existing retry branch — sets `fix_attempts=0`, `fix_context=None`, `status=QUEUED`, kicks the job. Stage stays `null`; the dispatcher assigns it at pickup.

`pause`, `resume`, and `skip_to_stage` remain rejected for `stage=null` rows.

### Surface 2 — coordinator scan (`src/coder_core/workers/coordinator.py`)

Add a second scan in `tick()`'s Phase 1:

```
WHERE status='queued' AND stage IS NULL
  AND role IN ('pm','architect','team-manager','developer','reviewer')
  AND created_at < cutoff
LIMIT 10
```

In `_process_task`, for a null-stage row: if `pool_capacity > 0`, kick the job and audit with `source_stage=null`; if `pool_capacity == 0`, log a skip — no stage flip (null is already "unclaimed", not "stuck executing"). The `LIMIT 10` cap prevents mass-dispatch on a recovering pool.

### Surface 3 — admin UI (`src/pages/TaskDetail.tsx`)

Extend `canRetry` to cover null-stage queued rows:

```
const DISPATCHER_ROLES = new Set(['pm','architect','team-manager','developer','reviewer']);
const canRetry =
  task.stage === 'stuck' || task.stage === 'rejected' ||
  (task.stage === null && task.status !== 'cancelled' && DISPATCHER_ROLES.has(task.role));
```

Unknown-role or cancelled retries surface as toasts via the existing `setActionError` path.

## Edge cases

**Concurrent override + coordinator tick.** Both call `dispatch_task(task_id)`. The `SELECT … FOR UPDATE SKIP LOCKED` lease in `dispatch_task` ensures only one execution wins; the other logs `"not leasable"` and no-ops.

**Task progresses between UI render and retry click.** The override handler reloads the row transactionally; if `status != QUEUED`, it returns a typed 409 before touching the row.

**The four stale ship-WIP tasks** (`460213bc`, `06b8a8cf`, `d4741b75`, `4e07947f`) have `status=cancelled`; the updated guard 409s them with `invalid_override`. `action: cancel` for remaining stage=null queued tasks is a follow-on spec.

**PM-draft calibration tasks specifically.** The existing `executing` stage in `orchestrate_task` covers PM; no new `pm_draft` stage needed. The simpler path: kick dispatcher, let orchestrator take over.

## Rollout

1. Deploy backend (`service.py` + `coordinator.py`). No migration, no flag — change narrows a 409 to correct scope.
2. Verify AC1: `POST .../tasks/36e0ed61/override {"action":"retry"}` → 200; task moves to `started_at != null` within one coordinator tick.
3. Verify AC2: saturate pool, dispatch fresh spec-run, observe stage=null architect/TM task, override → dispatches within one tick.
4. Deploy `TaskDetail.tsx`. Verify AC3: task with role outside `_RUNNERS` still 409s with `unknown_role`.
5. Backout: revert `service.py` to restore blanket guard. Coordinator widening is idempotent; safe to leave.

## Links

- Spec: [0092](../../product-specs/wip/0092-pm-retry-via-override.md)
- Related designs: [worker-communication](./worker-communication.md), [self-healing](./self-healing.md), [worker-dispatch-durability](./worker-dispatch-durability.md)
- Incident context: [coder-core#236](https://github.com/coder-devx/coder-core/pull/236) — founder approve handler that creates stage-null PM-draft tasks
