---
id: pipeline-operations
title: Pipeline operations
type: index
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-03
last_verified_at: 2026-05-03
implements_specs: [pipeline-operations]
related_designs: [system-overview, worker-communication, observability-and-cost-tracking, self-healing, escalations, branch-cleanup]
affects_services: [coder-core, coder-admin]
parent: system-overview
---

# Pipeline operations

The engineering shape of how tasks flow through a project's pipeline,
recover from stalls, and surface their state.

## What this category covers

Engineering counterpart of the
[pipeline-operations](../../product-specs/active/pipeline-operations.md)
spec. Groups the designs that govern task lifecycle, dispatch,
observability, and recovery.

## Components

- [worker-communication](./worker-communication.md) — how the
  orchestrator sequences workers; task-state machine; SSE event stream.
- [observability-and-cost-tracking](./observability-and-cost-tracking.md)
  — per-turn telemetry, token costs, prompt-cache hit rate, alert
  thresholds.
- [self-healing](./self-healing.md) — reaper that re-queues
  `running`-stuck tasks past the timeout threshold.
- [escalations](./escalations.md) — three-rung on-call ladder with
  quiet-hours and alert consolidation.
- [branch-cleanup](./branch-cleanup.md) — GC for the
  `task/<slug>` branches Developer workers create.

## Cross-cutting concerns

- **Auditability**: every dispatcher state transition emits an
  audit row — see [audit-log](./audit-log.md) (in
  [tenancy-and-access](./tenancy-and-access.md)).
- **Worker durability**: per spec 0056 each task runs in a per-task
  Cloud Run Job execution, not as a child of the HTTP service —
  prevents the "Cloud Run eviction kills the orchestrate_task task"
  failure mode.
- **Module boundaries**: the dispatcher seam is the
  ``WorkerDispatcher`` protocol per [coder-core-modular-monolith](./coder-core-modular-monolith.md).

## Links

- Specs: [pipeline-operations](../../product-specs/active/pipeline-operations.md)
- ADRs: [0011](../../adrs/0011-orphan-dispatch-reaper.md) (orphan reaper)
