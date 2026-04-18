# Designs Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Active — subject-named logical components

Logical components of the Coder system as it exists today.

| Slug | Title | Owner | Implements specs | Decided by |
|---|---|---|---|---|
| [architect-worker](./active/architect-worker.md) | Architect Worker | ro | [architect-worker](../product-specs/active/architect-worker.md) | — |
| [branch-cleanup](./active/branch-cleanup.md) | Branch cleanup | ro | [branch-cleanup](../product-specs/active/branch-cleanup.md) | — |
| [impersonation](./active/impersonation.md) | Impersonation | ro | — | [0006](../adrs/0006-per-role-service-accounts.md) |
| [knowledge-freshness](./active/knowledge-freshness.md) | Knowledge Freshness | ro | [knowledge-freshness](../product-specs/active/knowledge-freshness.md) | [0014](../adrs/0014-freshness-from-declared-affects.md) |
| [knowledge-repo-model](./active/knowledge-repo-model.md) | Knowledge Repo Model | ro | — | 0001, 0002, 0003, 0004, 0008 |
| [knowledge-write-api](./active/knowledge-write-api.md) | Knowledge Write API | ro | [knowledge-api](../product-specs/active/knowledge-api.md) | — |
| [observability-and-cost-tracking](./active/observability-and-cost-tracking.md) | Observability and Cost Tracking | ro | [observability](../product-specs/active/observability.md) | — |
| [pm-worker](./active/pm-worker.md) | PM Worker | ro | [pm-worker](../product-specs/active/pm-worker.md) | — |
| [system-overview](./active/system-overview.md) | System Overview | ro | — | 0001, 0005, 0006, 0007, 0008 |
| [team-manager-worker](./active/team-manager-worker.md) | Team Manager Worker | ro | [team-manager-worker](../product-specs/active/team-manager-worker.md) | — |
| [worker-communication](./active/worker-communication.md) | Worker Communication | ro | [task-orchestration](../product-specs/active/task-orchestration.md) | — |
| [worker-roles](./active/worker-roles.md) | Worker Roles | ro | — | 0006, 0007 |

## WIP — numbered, roadmap-aligned

| ID | Title | Owner | Implements specs |
|---|---|---|---|
| [0002](./wip/0002-competitive-intelligence-pipeline.md) | Competitive Intelligence Pipeline | ro | — |
| [0029](./wip/0029-prompt-caching.md) | Prompt caching & shared context reuse | ro | [0029](../product-specs/wip/0029-prompt-caching.md) |
| [0030](./wip/0030-model-tier-routing.md) | Model tier routing | ro | [0030](../product-specs/wip/0030-model-tier-routing.md) |
| [0031](./wip/0031-token-budgets.md) | Per-project token budgets & cost gates | ro | [0031](../product-specs/wip/0031-token-budgets.md) |
| [0032](./wip/0032-cost-regression-alerts.md) | Prompt & cost regression alerts | ro | [0032](../product-specs/wip/0032-cost-regression-alerts.md) |

## Deprecated

_None yet._
