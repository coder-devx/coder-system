# Product specs — index

> Curated entry point to the product surface of the **Coder System**.
> Workers (PM, Architect, Team Manager, Reviewer) and humans should
> start here when grounding on the existing product. The
> [registry](./registry.yaml) is the flat machine-readable list;
> this is the navigable tree.

## What Coder is

Coder is an end-to-end system for building and operating software
products with autonomous agent teams. One Coder system manages many
**projects** in parallel; each project has its own **team** of
**workers** that fill **roles** (Architect, PM, Team Manager,
Developer, Reviewer, …). Workers act on behalf of their project
against external systems (GitHub, GCP, Slack, Notion, Anthropic). A
human user interacts via an Admin Panel for status, debugging, and
override.

The product surface organises into five categories. Each category is
its own active spec — drill into the linked file for the category's
overview and component list, then into the specific component spec
from there.

## Pipeline operations

How the system runs work through a project's pipeline reliably,
keeps it observable, and recovers when it stalls.
→ [pipeline-operations](./active/pipeline-operations.md)

- [task-orchestration](./active/task-orchestration.md) — task lifecycle, dispatcher, stage transitions
- [observability](./active/observability.md) — per-task telemetry, token costs, pipeline metrics
- [self-healing](./active/self-healing.md) — reaper for stuck tasks past timeout
- [escalations](./active/escalations.md) — three-rung on-call ladder with quiet hours
- [branch-cleanup](./active/branch-cleanup.md) — automatic GC of stale Developer feature branches

## Worker roles

The team of role-specialised agents that fill a project's pipeline.
Each worker has one job, one set of tools, one output shape, one
place in the flow.
→ [worker-roles](./active/worker-roles.md)

- [pm-worker](./active/pm-worker.md) — Product Manager: specs and acceptance
- [architect-worker](./active/architect-worker.md) — Software Architect: designs, ADRs, system shape
- [team-manager-worker](./active/team-manager-worker.md) — Team Manager: spec → developer-task decomposition
- [developer-worker](./active/developer-worker.md) — Developer: code, tests, PRs
- [reviewer-worker](./active/reviewer-worker.md) — Reviewer: technical-quality gate before PM acceptance

## Tenancy & access

How one Coder deployment serves many projects without crossing wires
and how every action is attributed to a real actor.
→ [tenancy-and-access](./active/tenancy-and-access.md)

- [multi-tenancy](./active/multi-tenancy.md) — `project_id` everywhere invariant
- [impersonation](./active/impersonation.md) — short-lived role-scoped bearer tokens
- [service-accounts](./active/service-accounts.md) — per-role GCP service accounts, brokered escalations
- [audit-log](./active/audit-log.md) — every mutation recorded with actor, action, before/after

## Knowledge & admin

How a project's knowledge is read, written, kept current, and
surfaced to the human operator.
→ [knowledge-and-admin](./active/knowledge-and-admin.md)

- [knowledge-api](./active/knowledge-api.md) — read-through layer with per-project cache
- [knowledge-freshness](./active/knowledge-freshness.md) — automatic stale-artifact detection + rewrites
- [admin-panel](./active/admin-panel.md) — user-facing SPA for status, debug, override
- [onboarding](./active/onboarding.md) — how a new project gets wired into Coder

## Delivery & infra

How code reaches production and how the system itself stays
maintainable.
→ [delivery-and-infra](./active/delivery-and-infra.md)

- [continuous-deployment](./active/continuous-deployment.md) — push-to-main CD with health-checks
- [tenant-isolation](./active/tenant-isolation.md) — test-suite harness for the multi-tenancy contract
- [0051-coder-core-modular-monolith](./active/0051-coder-core-modular-monolith.md) — module-boundary contracts

## WIP — roadmap-aligned specs in flight

The numbered specs under [`wip/`](./wip/) describe planned work
aligned with the roadmap. They land into active components above
when they ship (see AGENTS.md rule 5 for the wip → active merge
shape). See [registry.yaml](./registry.yaml) for the full list.

## How to use this index

- **Drafting a new spec** (PM): start here, find the category your
  problem statement fits in, follow the link to the category spec,
  then to the relevant existing components. Reference the existing
  spec under `related_specs` and pick a parent.
- **Designing for a spec** (Architect): same. The category spec lists
  its served-by designs.
- **Decomposing a spec into tasks** (Team Manager): the category
  spec's "Cross-cutting concerns" section names the integration
  points that any developer task will touch.
- **Reviewing** (Reviewer): use the parent + related_specs to spot
  drift between the change and the active design.

## Layout

Per [design 0062](../designs/wip/0062-navigation-tree-pattern.md),
each spec carries a `parent:` field pointing at its category. The
inverse view (children of a category) is derived; don't hand-maintain
both. Re-parenting a spec is a 1-line frontmatter change plus a
registry update.
