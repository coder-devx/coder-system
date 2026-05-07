---
id: pipeline-operations
title: Pipeline operations
type: index
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-03
last_verified_at: 2026-05-03
summary: "How tasks flow reliably through a project's pipeline, stay observable, and recover when stalled."
served_by_designs: [worker-communication, observability-and-cost-tracking, escalations, self-healing, branch-cleanup]
related_specs: [worker-roles, tenancy-and-access]
parent: ~
---

# Pipeline operations

How the Coder system runs work through a project's pipeline reliably,
keeps it observable while it runs, and recovers when it stalls.

## What this category covers

Tasks flow through a multi-stage pipeline (PM draft → Architect design →
Team Manager decompose → Developer build → Reviewer review → PM accept).
This category groups the specs that govern the *operation* of that
pipeline — how a task moves between stages, how stuck pipelines get
unstuck, what's measured along the way, and how on-call humans get
paged when automation can't continue.

## Components

- [task-orchestration](./task-orchestration.md) — task lifecycle
  state machine, dispatcher leasing, stage transitions.
- [observability](./observability.md) — per-task telemetry, token
  costs, pipeline metrics surfaced to the admin panel.
- [self-healing](./self-healing.md) — reaper that re-queues stuck
  pipelines and tasks past their timeout.
- [escalations](./escalations.md) — three-rung on-call ladder
  (developer → on-call → user) with quiet hours and consolidation.
- [branch-cleanup](./branch-cleanup.md) — automatic GC of stale
  feature branches the Developer worker created.

## Cross-cutting concerns

- **Audit trail**: every state transition surfaces through
  [audit-log](./audit-log.md) (in [tenancy-and-access](./tenancy-and-access.md)).
- **Tenant isolation**: pipeline state is project-scoped; see
  [multi-tenancy](./multi-tenancy.md).
- **Visibility**: the [admin-panel](./admin-panel.md) is the human
  surface for everything in this category.

## Links

- Designs: [worker-communication](../../designs/active/worker-communication.md),
  [observability-and-cost-tracking](../../designs/active/observability-and-cost-tracking.md),
  [self-healing](../../designs/active/self-healing.md),
  [escalations](../../designs/active/escalations.md),
  [branch-cleanup](../../designs/active/branch-cleanup.md)
