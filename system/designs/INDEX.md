# Designs — index

> Curated entry point to the engineering surface of the **Coder
> System**. Workers (Architect, Reviewer) and humans should start
> here when grounding on the existing engineering. The
> [registry](./registry.yaml) is the flat machine-readable list;
> this is the navigable tree.

## Root

The system-overview design is the single big-picture engineering
entry point. Read it first if you're new.

→ [system-overview](./active/system-overview.md)

## Categories

The engineering surface mirrors the product-spec categories
([INDEX](../product-specs/INDEX.md) on the product side):

### Pipeline operations

How tasks flow, how stalls recover, how state surfaces.
→ [pipeline-operations](./active/pipeline-operations.md)

- [worker-communication](./active/worker-communication.md) — task-state machine, dispatcher, SSE
- [observability-and-cost-tracking](./active/observability-and-cost-tracking.md) — telemetry, cost, alerts
- [self-healing](./active/self-healing.md) — orphan-task reaper
- [escalations](./active/escalations.md) — on-call ladder
- [branch-cleanup](./active/branch-cleanup.md) — stale-branch GC

### Worker roles

The role-typed worker subprocesses, their input contract, and how
they compose into a pipeline.
→ [worker-roles](./active/worker-roles.md)

- [pm-worker](./active/pm-worker.md) — PM (draft / accept)
- [architect-worker](./active/architect-worker.md) — Architect (design / audit / ship)
- [team-manager-worker](./active/team-manager-worker.md) — Team Manager (decompose)

### Tenancy & access

Multi-tenancy enforcement and actor attribution.
→ [tenancy-and-access](./active/tenancy-and-access.md)

- [impersonation](./active/impersonation.md) — short-lived role-scoped tokens
- [audit-log](./active/audit-log.md) — `record_audit_event` + `audit_events` table
- [tenant-isolation](./active/tenant-isolation.md) — cross-tenant test harness

### Knowledge stack

How each project's knowledge repo is served, written, and kept fresh.
→ [knowledge-stack](./active/knowledge-stack.md)

- [knowledge-repo-model](./active/knowledge-repo-model.md) — repo shape, knowledge-types contract
- [knowledge-write-api](./active/knowledge-write-api.md) — HTTP write surface
- [knowledge-freshness](./active/knowledge-freshness.md) — freshness audit + rewrites

### Coder-core architecture

The shape of the orchestrator service itself.

- [0051-coder-core-modular-monolith](./active/0051-coder-core-modular-monolith.md) — module boundaries, import-linter contracts

## WIP — roadmap-aligned designs in flight

Numbered designs under [`wip/`](./wip/) describe planned work. They
fold into one or more active designs above when they ship (per
AGENTS.md rule 5). See [registry.yaml](./registry.yaml) for the full
list. Recent and high-leverage:

- [0057](./wip/0057-role-prompt-knowledge-layout.md) — per-role/per-mode prompt layout (shipped)
- [0062](./wip/0062-navigation-tree-pattern.md) — this navigation pattern

## How to use this index

- **Designing for a spec** (Architect): start at the spec's
  category in [product-specs/INDEX.md](../product-specs/INDEX.md),
  follow the link to the engineering category here, then to the
  specific component design.
- **Reviewing a PR** (Reviewer): use the active design that matches
  the change's surface to spot drift.
- **Planning a cycle** (Team Manager + PM + Architect): read
  category-level designs to understand cross-cutting integration
  points before decomposing into tasks.

## Layout

Per [design 0062](./wip/0062-navigation-tree-pattern.md), each
design carries a `parent:` field pointing at its category. The
inverse (children of a category) is derived. Re-parenting a design
is a 1-line frontmatter change plus a registry update.
