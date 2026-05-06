# Product Specs Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Active — subject-named logical components

Components of the Coder system as it exists today. Ship history lives
in each component's `## Evolution` section and in git.

| Slug | Title | Owner | Served by designs |
|---|---|---|---|
| [admin-panel](./active/admin-panel.md) | Admin Panel | ro | [admin-panel](../designs/active/admin-panel.md) |
| [architect-worker](./active/architect-worker.md) | Architect Worker | ro | [architect-worker](../designs/active/architect-worker.md) |
| [audit-log](./active/audit-log.md) | Audit log | ro | [audit-log](../designs/active/audit-log.md) |
| [branch-cleanup](./active/branch-cleanup.md) | Branch cleanup | ro | [branch-cleanup](../designs/active/branch-cleanup.md) |
| [cold-start-ingestion](./active/cold-start-ingestion.md) | Cold-start knowledge ingestion | ro | — |
| [continuous-deployment](./active/continuous-deployment.md) | Continuous Deployment | ro | [continuous-deployment](../designs/active/continuous-deployment.md) |
| [delivery-and-infra](./active/delivery-and-infra.md) | Delivery & infra | ro | [system-overview](../designs/active/system-overview.md), 0051 |
| [developer-worker](./active/developer-worker.md) | Developer Worker | ro | [developer-worker](../designs/active/developer-worker.md) |
| [escalations](./active/escalations.md) | Escalations & on-call routing | ro | [escalations](../designs/active/escalations.md) |
| [fleet-patterns](./active/fleet-patterns.md) | Fleet pattern surfacing | ro | — |
| [impersonation](./active/impersonation.md) | Impersonation | ro | [impersonation](../designs/active/impersonation.md) |
| [knowledge-and-admin](./active/knowledge-and-admin.md) | Knowledge & admin | ro | [knowledge-repo-model](../designs/active/knowledge-repo-model.md), [knowledge-write-api](../designs/active/knowledge-write-api.md), [knowledge-freshness](../designs/active/knowledge-freshness.md) |
| [knowledge-api](./active/knowledge-api.md) | Knowledge API | ro | [knowledge-write-api](../designs/active/knowledge-write-api.md), [knowledge-repo-model](../designs/active/knowledge-repo-model.md) |
| [knowledge-freshness](./active/knowledge-freshness.md) | Knowledge Freshness | ro | [knowledge-freshness](../designs/active/knowledge-freshness.md) |
| [knowledge-schema-migration](./active/knowledge-schema-migration.md) | Knowledge schema migration | ro | — |
| [managed-workflows](./active/managed-workflows.md) | Managed-repo workflow distribution | ro | — |
| [mcp-agent-interface](./active/mcp-agent-interface.md) | MCP agent interface | ro | — |
| [multi-tenancy](./active/multi-tenancy.md) | Multi-tenancy | ro | [multi-tenancy](../designs/active/multi-tenancy.md) |
| [oauth-mcp](./active/oauth-mcp.md) | OAuth 2.1 for MCP clients | ro | 0050 |
| [observability](./active/observability.md) | Observability | ro | [observability-and-cost-tracking](../designs/active/observability-and-cost-tracking.md) |
| [onboarding](./active/onboarding.md) | Onboarding | ro | [onboarding](../designs/active/onboarding.md) |
| [pipeline-operations](./active/pipeline-operations.md) | Pipeline operations | ro | [worker-communication](../designs/active/worker-communication.md), [observability-and-cost-tracking](../designs/active/observability-and-cost-tracking.md), [escalations](../designs/active/escalations.md), [self-healing](../designs/active/self-healing.md), [branch-cleanup](../designs/active/branch-cleanup.md) |
| [pm-worker](./active/pm-worker.md) | PM Worker | ro | [pm-worker](../designs/active/pm-worker.md) |
| [reviewer-worker](./active/reviewer-worker.md) | Reviewer Worker | ro | [reviewer-worker](../designs/active/reviewer-worker.md) |
| [secret-rotation](./active/secret-rotation.md) | Automated secret rotation | ro | — |
| [self-healing](./active/self-healing.md) | Self-healing stuck pipelines | ro | [self-healing](../designs/active/self-healing.md) |
| [service-accounts](./active/service-accounts.md) | Service Accounts | ro | [service-accounts](../designs/active/service-accounts.md) |
| [task-orchestration](./active/task-orchestration.md) | Task Orchestration | ro | [worker-communication](../designs/active/worker-communication.md) |
| [team-manager-worker](./active/team-manager-worker.md) | Team Manager Worker | ro | [team-manager-worker](../designs/active/team-manager-worker.md) |
| [tenancy-and-access](./active/tenancy-and-access.md) | Tenancy & access | ro | [impersonation](../designs/active/impersonation.md), [audit-log](../designs/active/audit-log.md), [tenant-isolation](../designs/active/tenant-isolation.md) |
| [tenant-isolation](./active/tenant-isolation.md) | Tenant isolation test harness | ro | [tenant-isolation](../designs/active/tenant-isolation.md) |
| [worker-roles](./active/worker-roles.md) | Worker roles | ro | [worker-roles](../designs/active/worker-roles.md), [architect-worker](../designs/active/architect-worker.md), [pm-worker](../designs/active/pm-worker.md), [team-manager-worker](../designs/active/team-manager-worker.md) |

## WIP — numbered, roadmap-aligned

| ID | Title | Owner | Served by designs |
|---|---|---|---|
| [0065](./wip/0065-reviewer-scope-and-turn-cap.md) | Reviewer scope cut + turn cap | ro | — |

## Deprecated

_None yet._
