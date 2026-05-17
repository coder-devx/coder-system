---
id: worker-roles
title: Worker roles
type: index
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-03
last_verified_at: 2026-05-03
summary: "The team of role-specialised agents that fill a project's pipeline."
served_by_designs: [architect-worker, pm-worker, team-manager-worker]
related_specs: [architect-worker, developer-worker, impersonation, knowledge-and-admin, observability, pipeline-operations, pm-worker, reviewer-worker, service-accounts, task-orchestration, team-manager-worker, tenancy-and-access]
parent: ~
---

# Worker roles

The team of autonomous agent roles that fill a project's pipeline.

## What this category covers

A Coder project is staffed by a *team* of role-specialised workers.
Each worker is a focused agent: it has one job, one set of tools, one
output shape, and one place in the pipeline. This category groups the
specs that define each role's contract — what it owns, what it
produces, where it sits in the flow.

The shared role contract (capabilities, permissions, prompts, tools,
escalation paths) lives at
[`system/roles/`](../../roles/REGISTRY.md). This category covers the
*product* surface of those roles: what the team produces and how the
roles compose into the pipeline.

## Components

- [pm-worker](./workers/pm-worker.md) — Product Manager: owns specs and
  acceptance. Bookends the pipeline (drafts at the start, judges at
  the end).
- [architect-worker](./workers/architect-worker.md) — Software Architect:
  designs, ADRs, system shape.
- [team-manager-worker](./workers/team-manager-worker.md) — Team Manager:
  decomposes specs/designs into sequenced developer tasks.
- [developer-worker](./workers/developer-worker.md) — Developer: writes code,
  writes tests, opens PRs.
- [reviewer-worker](./workers/reviewer-worker.md) — Reviewer: technical-quality
  gate before PM acceptance.

## Pipeline shape

```
PM (draft spec)  →  Architect (design)  →  Team Manager (decompose)
                                                    ↓
                          ←  Reviewer (code review)  ←  Developer (build)
                          ↓
                       PM (accept) → spec promotes wip → active
```

## Cross-cutting concerns

- **Identity & impersonation**: every worker runs under a
  short-lived role-scoped credential — see
  [impersonation](./tenancy/impersonation.md), [service-accounts](./tenancy/service-accounts.md).
- **Observability**: per-worker token costs and turn counts surface
  through [observability](./pipeline/observability.md).
- **Communication**: workers don't talk to each other in real time;
  the orchestrator sequences them — see
  [task-orchestration](./pipeline/task-orchestration.md).

## Links

- Roles registry: [`../../roles/REGISTRY.md`](../../roles/REGISTRY.md)
- Designs: [worker-roles](../../designs/active/worker-roles.md),
  [architect-worker](../../designs/active/workers/architect-worker.md),
  [pm-worker](../../designs/active/workers/pm-worker.md),
  [team-manager-worker](../../designs/active/workers/team-manager-worker.md)
