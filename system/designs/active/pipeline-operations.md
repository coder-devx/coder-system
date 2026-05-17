---
id: pipeline-operations
title: Pipeline operations
type: index
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-03
last_verified_at: 2026-05-03
summary: How tasks flow, how stalls recover, how state surfaces.
implements_specs: [pipeline-operations]
related_designs: [system-overview, worker-communication, observability-and-cost-tracking, self-healing, escalations, branch-cleanup]
affects_services: [coder-core, coder-admin]
parent: ~
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

**Dispatch & lifecycle:**

- [dispatcher](./pipeline/dispatcher.md) — SKIP LOCKED lease, per-project fair queue, claude-CLI spawn, terminal-status writeback.
- [task-lifecycle](./pipeline/task-lifecycle.md) — orthogonal status × stage machine; override actions (`retry` / `resume` / `skip_to_stage` / `pause` / `reject`).
- [worker-communication](./pipeline/worker-communication.md) — how the orchestrator sequences workers; task-state machine; SSE event stream.
- [worker-dispatch-durability](./pipeline/worker-dispatch-durability.md) — moving worker subprocess execution out of the HTTP service into per-task Cloud Run Jobs (spec 0056).
- [orchestrator-github-state-reconciliation](./pipeline/orchestrator-github-state-reconciliation.md) — keep `tasks` rows in sync with the underlying GitHub PR state.

**Recovery:**

- [self-healing](./pipeline/self-healing.md) — reaper that re-queues `running`-stuck tasks past the timeout threshold.
- [escalations](./pipeline/escalations.md) — three-rung on-call ladder with quiet-hours and alert consolidation.
- [stuck-pipeline-slack-paging](./pipeline/stuck-pipeline-slack-paging.md) — page Slack at the 15-minute stuck threshold.
- [post-pr-ci-fix-loop](./pipeline/post-pr-ci-fix-loop.md) — bounded CI-failure fix loop after Developer PRs land.
- [branch-cleanup](./pipeline/branch-cleanup.md) — GC for the `task/<slug>` branches Developer workers create.

**Observability & cost:**

- [observability-and-cost-tracking](./pipeline/observability-and-cost-tracking.md) — per-turn telemetry, token costs, prompt-cache hit rate, alert thresholds.
- [cost-regression-alerts](./pipeline/cost-regression-alerts.md) — alerts when prompt or per-task cost regresses past threshold.
- [token-budgets-and-cost-gates](./pipeline/token-budgets-and-cost-gates.md) — per-project token budgets and pre-spawn cost gate.
- [model-tier-routing](./pipeline/model-tier-routing.md) — route low-complexity tasks to Haiku, reserve Sonnet for design work.
- [prompt-caching-architecture](./pipeline/prompt-caching-architecture.md) — cacheable-prefix discipline; shared context across one pipeline run.
- [confidence-auto-approval](./pipeline/confidence-auto-approval.md) — confidence-scored auto-approval for low-risk worker outputs.

## Cross-cutting concerns

- **Auditability**: every dispatcher state transition emits an
  audit row — see [audit-log](./tenancy/audit-log.md) (in
  [tenancy-and-access](./tenancy-and-access.md)).
- **Worker durability**: per spec 0056 each task runs in a per-task
  Cloud Run Job execution, not as a child of the HTTP service —
  prevents the "Cloud Run eviction kills the orchestrate_task task"
  failure mode.
- **Module boundaries**: the dispatcher seam is the
  ``WorkerDispatcher`` protocol per [coder-core-modular-monolith](./delivery/coder-core-modular-monolith.md).

## Links

- Specs: [pipeline-operations](../../product-specs/active/pipeline-operations.md)
- ADRs: [0011](../../adrs/0011-orphan-dispatch-reaper.md) (orphan reaper)
