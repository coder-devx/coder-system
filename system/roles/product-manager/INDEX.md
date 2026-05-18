# PM — Reading Map

> Per [design 0095](../../designs/wip/0095-role-scoped-knowledge-layout-and-cached-workspace-context.md).
> Routes by spec topic to the relevant product-specs (for prior art on
> AC patterns) and design-rollups (for engineering context). The
> designs tree entry is [`system/designs/INDEX.md`](../../designs/INDEX.md).

## Always load

- [`designs/active/system-overview.md`](../../designs/active/system-overview.md) — what the platform does, who the operators are
- [`glossary.md`](../../glossary.md) — shared vocabulary (workers, roles, projects, stages)
- [`product-specs/REGISTRY.md`](../../product-specs/REGISTRY.md) — what specs exist, what's active vs WIP
- This role doc — AC patterns and the user-observable bar live in [`role.md`](./role.md) §"What a good spec looks like"

## Route by topic (draft mode — `draft: <problem>`)

For a spec drafting task, load these to ground the problem statement and
parent category before writing.

| If the problem touches… | Reads to ground the spec |
|---|---|
| **Pipeline reliability / stalls / retries** | Specs: [pipeline-operations](../../product-specs/active/pipeline-operations.md), [self-healing](../../product-specs/active/pipeline/self-healing.md), [escalations](../../product-specs/active/pipeline/escalations.md). Engineering context: **[pipeline-operations design rollup](../../designs/active/pipeline-operations.md)** — for stall-stage / timeout / lifecycle topics also fetch **[task-lifecycle](../../designs/active/pipeline/task-lifecycle.md)** (defines the orthogonal status × stage machine) |
| **Worker behavior / role boundaries** | Specs: [worker-roles](../../product-specs/active/worker-roles.md) + the per-role spec ([architect](../../product-specs/active/workers/architect-worker.md), [developer](../../product-specs/active/workers/developer-worker.md), [pm](../../product-specs/active/workers/pm-worker.md), [reviewer](../../product-specs/active/workers/reviewer-worker.md), [team-manager](../../product-specs/active/workers/team-manager-worker.md)). Engineering context: **[worker-roles design rollup](../../designs/active/worker-roles.md)** |
| **Knowledge / specs / designs / freshness** | Specs: [knowledge-api](../../product-specs/active/knowledge/knowledge-api.md), [knowledge-freshness](../../product-specs/active/knowledge/knowledge-freshness.md), [knowledge-and-admin](../../product-specs/active/knowledge-and-admin.md). Engineering context: **[knowledge-and-admin design rollup](../../designs/active/knowledge-and-admin.md)**. **Do not read worker internals (`src/coder_core/workers/*.py`) to ground a spec** — those are architect inputs; the question they would answer goes in `## Open questions` for the architect to resolve. |
| **Tenancy / impersonation / audit** | Specs: [tenancy-and-access](../../product-specs/active/tenancy-and-access.md), [audit-log](../../product-specs/active/tenancy/audit-log.md), [impersonation](../../product-specs/active/tenancy/impersonation.md). Engineering context: **[tenancy-and-access design rollup](../../designs/active/tenancy-and-access.md)** |
| **Admin panel surfaces** | Specs: [admin-panel](../../product-specs/active/knowledge/admin-panel.md). Engineering context: **[knowledge-and-admin design rollup](../../designs/active/knowledge-and-admin.md)** → [admin-panel](../../designs/active/knowledge/admin-panel.md), [navigation-tree-pattern](../../designs/active/knowledge/navigation-tree-pattern.md) |
| **Cost / observability / metrics** | Specs: [observability](../../product-specs/active/pipeline/observability.md). Engineering context: **[pipeline-operations design rollup](../../designs/active/pipeline-operations.md)** § Observability |
| **Spec authoring discipline / quality bar** | This file's parent [`role.md`](./role.md) §"What a good spec looks like" + [`tasks/draft.md`](./tasks/draft.md) checklist + [`product-specs/_TEMPLATE.md`](../../product-specs/_TEMPLATE.md) for body shape. These three are the PM-owned source of truth for line caps, section discipline, AC structure, and `parent:` routing — no active spec mirrors them. |

## Route by topic (accept mode — `accept: <spec_id>`)

Accept mode has a source clone (workspace.yaml lists `auth-mode: accept`).
Use the local repo for AC verification — not `gh api`. Order of evidence
per [`tasks/accept.md`](./tasks/accept.md): merged PR with passing CI →
metric/screenshot from the running admin panel → test-env walk-through →
read source only when no user-observable surface exists. The last is a
*last resort* — flag it in the verdict if you had to fall back to it.

## When to read background / ADRs

PMs rarely need ADRs at draft time — they describe engineering decisions,
not user-facing contracts. Read [ADR 0007 (reviewer-separated-from-pm)](../../adrs/0007-reviewer-separated-from-pm.md)
once to internalize the PM/Reviewer split, then mostly ignore the ADR
folder unless a spec proposal collides with one (the audit pipeline
will flag this).

## Notes on this file

- Lives at `system/roles/product-manager/INDEX.md`. Loaded by the PM worker
  as part of its cached system prompt (per design 0095 phase 5a).
- Routes are stable identifiers — when active artifacts move within
  the designs tree, this table updates in place.
- PM is the **PM of the Coder System** — operators of the admin panel,
  pipeline workers, project owners. Frame user pain in those terms.
