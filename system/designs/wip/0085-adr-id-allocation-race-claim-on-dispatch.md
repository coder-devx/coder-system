---
id: 0085
title: ADR ID Allocation Race — Claim-on-Dispatch
type: design
status: wip
owner: ro
created: '2026-05-12'
updated: '2026-05-12'
last_verified_at: '2026-05-12'
implements_specs:
- task-orchestration
decided_by: []
related_designs:
- architect-worker
- worker-dispatch-durability
affects_services:
- coder-core
affects_repos:
- coder-core
parent: pipeline-operations
---

# ADR ID Allocation Race — Claim-on-Dispatch

## Context

When two architect tasks are admitted concurrently, both read `max(adrs.registry) + 1` from `main` and receive the same `Next free ADR ID`. The second batch to commit collides; ADRs are silently dropped. This is orchestrator gap #1 (spec 0085); coder-core#204 fixed a YAML-parse symptom without closing the race. The fix: claim IDs atomically at admission via a new DB table.

## Goals / non-goals

**Goals:** Non-overlapping ADR ranges for concurrent admits; durable reservation in the orchestrator DB; release on no-commit terminal so IDs aren't leaked forever.

**Non-goals:** Refactoring the ADR registry format; cross-project reservation; changing the operator-override path.

## Design

```mermaid
sequenceDiagram
  participant D1 as Dispatcher (T_A)
  participant D2 as Dispatcher (T_B)
  participant DB as adr_id_reservations
  participant R  as ADR Registry

  D1->>DB: BEGIN; SELECT max(range_end) WHERE project=p → 36; INSERT (start=37,end=46); COMMIT
  D2->>DB: BEGIN; SELECT max(range_end) WHERE project=p → 46; INSERT (start=47,end=56); COMMIT
  D1-->>D1: run-context "Next free ADR ID: 0037"
  D2-->>D2: run-context "Next free ADR ID: 0047"
  D1->>R: commit ADRs 0037, 0038 — no collision
  D2->>R: commit ADRs 0047, 0048 — no collision
```

### `adr_id_reservations` table (new Alembic migration)

```sql
CREATE TABLE adr_id_reservations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   TEXT NOT NULL,
    task_id      UUID NOT NULL REFERENCES tasks(id),
    range_start  INTEGER NOT NULL,
    range_end    INTEGER NOT NULL,
    claimed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at  TIMESTAMPTZ NULL,
    UNIQUE (project_id, range_start)
);
CREATE INDEX ON adr_id_reservations (project_id, released_at);
```

`UNIQUE (project_id, range_start)` is the serialization lock. Concurrent inserts with the same `range_start` race on the constraint; the loser retries once, re-reads the new max, and claims the next slab.

### `_compute_id_hints()` — claim path (`dispatcher.py`)

Replaces the read-only `max(registry) + 1` allocation for ADR IDs:

1. DB transaction: `SELECT max(range_end) FROM adr_id_reservations WHERE project_id=? AND released_at IS NULL`.
2. Read `max(id)` from `system/adrs/registry.yaml` (existing logic, unchanged).
3. `next_start = max(registry_max, reservation_max) + 1`. Slab size: 10 (`range_end = next_start + 9`).
4. Insert reservation row. On `UniqueViolation`, retry once from step 1.
5. Return `f"{next_start:04d}"` as `Next free ADR ID` in run-context.

Wrapped in `try/except OperationalError` to fall back to the legacy read-only path if the table doesn't yet exist (zero-downtime migration window).

### Terminal-state release — `_maybe_release_adr_reservation(task_id, project_id)`

Called from `_handle_architect_result` (Phase 4 success path), the `TIMED_OUT` path, and the `CANCELLED` path.

- Read the task's reservation row. If none (pre-migration task or standalone), return.
- Count ADRs committed in `[range_start, range_end]` by reading `system/adrs/registry.yaml` and filtering numeric IDs in the range.
- If zero committed: `UPDATE adr_id_reservations SET released_at=now() WHERE task_id=?` — IDs become reusable for the next admit.
- If any committed: leave the row as a history sentinel. Gaps at uncommitted IDs in the range are intentional.

### Edge cases

- **Constraint race:** Two admits within milliseconds both attempt the same `range_start`. One wins; the other gets `UniqueViolation`, retries, reads the winner's `range_end`, claims the next slab. Net: zero collision, one retry at most.
- **Reaper terminal (`TIMED_OUT`):** The self-heal reaper marks the task `timed_out`; the terminal hook fires `_maybe_release_adr_reservation`. Since no ADRs committed, `released_at` is set and the slab is freed for the next dispatch.
- **Partial commit (AC4):** Architect emits 1 of an allocated 10 IDs and reaches terminal. Release check sees count > 0; reservation stays; the uncommitted IDs are an accepted registry gap.
- **Pre-migration window:** `OperationalError` fallback in `_compute_id_hints()` returns the legacy allocation. The table migration is additive DDL (no lock on `tasks`); the window where the code is deployed but the table is absent is seconds.

## Rollout

1. **Migration:** Deploy Alembic migration (additive DDL, zero downtime). Table exists before any new code reads it.
2. **Code deploy:** Ship `dispatcher.py` changes gated by `CODER_ADR_CLAIM_ON_DISPATCH` env flag (default `false`). `OperationalError` fallback is belt-and-suspenders during the window.
3. **Soak on `coder` project (1–2 days):** Enable flag for `coder` only. Run AC5 manual test: 20 concurrent architect dispatches in a 100 ms window; verify no `collision` failure_kinds and contiguous non-overlapping ADR ranges.
4. **Fleet enable:** Set `CODER_ADR_CLAIM_ON_DISPATCH=true` fleet-wide. After 1 week clean, remove the `OperationalError` fallback and the env flag.

## Open questions

- **Slab size (10):** Generous for v1. If audit tooling flags numeric gaps as errors in the future, lower to 5 or switch to tight (exact-count) allocation.
- **Release check via GitHub read:** Acceptable at terminal-state frequency (once per task). If a `knowledge_freshness` DB cache table lands later (knowledge-stack design), prefer querying it over the network read.

## Links

- Spec: [0085 — ADR ID allocation race](../../product-specs/wip/0085-adr-id-allocation-race-under-concurrent-dispatch.md)
- Pair spec: [0086 — architect-adr-collision-failure-kind](../../product-specs/wip/0086-architect-adr-collision-failure-kind.md)
- ADR 0028: allocation guard — dispatcher-inject-or-refuse; this extends its reservation semantics
- Design: [architect-worker](./architect-worker.md) — extends the admission path and Phase 4 handler
- Design: [worker-dispatch-durability](./worker-dispatch-durability.md) — Cloud Run Job context for the dispatcher
- Design: [pipeline-operations](./pipeline-operations.md) — parent category
