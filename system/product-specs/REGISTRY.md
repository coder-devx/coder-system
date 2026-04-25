# Product Specs Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Active — subject-named logical components

Components of the Coder system as it exists today. Ship history lives
in each component's `## Evolution` section and in git.

| Slug | Title | Owner | Served by designs |
|---|---|---|---|
| [admin-panel](./active/admin-panel.md) | Admin Panel | ro | [system-overview](../designs/active/system-overview.md) |
| [architect-worker](./active/architect-worker.md) | Architect Worker | ro | [architect-worker](../designs/active/architect-worker.md) |
| [audit-log](./active/audit-log.md) | Audit log | ro | [audit-log](../designs/active/audit-log.md) |
| [branch-cleanup](./active/branch-cleanup.md) | Branch cleanup | ro | [branch-cleanup](../designs/active/branch-cleanup.md) |
| [continuous-deployment](./active/continuous-deployment.md) | Continuous Deployment | ro | [system-overview](../designs/active/system-overview.md) |
| [developer-worker](./active/developer-worker.md) | Developer Worker | ro | [worker-roles](../designs/active/worker-roles.md) |
| [escalations](./active/escalations.md) | Escalations & on-call routing | ro | [escalations](../designs/active/escalations.md) |
| [impersonation](./active/impersonation.md) | Impersonation | ro | [impersonation](../designs/active/impersonation.md) |
| [knowledge-api](./active/knowledge-api.md) | Knowledge API | ro | [knowledge-write-api](../designs/active/knowledge-write-api.md), [knowledge-repo-model](../designs/active/knowledge-repo-model.md) |
| [knowledge-freshness](./active/knowledge-freshness.md) | Knowledge Freshness | ro | [knowledge-freshness](../designs/active/knowledge-freshness.md) |
| [multi-tenancy](./active/multi-tenancy.md) | Multi-tenancy | ro | [system-overview](../designs/active/system-overview.md) |
| [observability](./active/observability.md) | Observability | ro | [observability-and-cost-tracking](../designs/active/observability-and-cost-tracking.md) |
| [onboarding](./active/onboarding.md) | Onboarding | ro | [system-overview](../designs/active/system-overview.md) |
| [pm-worker](./active/pm-worker.md) | PM Worker | ro | [pm-worker](../designs/active/pm-worker.md) |
| [reviewer-worker](./active/reviewer-worker.md) | Reviewer Worker | ro | [worker-roles](../designs/active/worker-roles.md) |
| [self-healing](./active/self-healing.md) | Self-healing stuck pipelines | ro | [self-healing](../designs/active/self-healing.md) |
| [service-accounts](./active/service-accounts.md) | Service Accounts | ro | [worker-roles](../designs/active/worker-roles.md) |
| [task-orchestration](./active/task-orchestration.md) | Task Orchestration | ro | [worker-communication](../designs/active/worker-communication.md) |
| [team-manager-worker](./active/team-manager-worker.md) | Team Manager Worker | ro | [team-manager-worker](../designs/active/team-manager-worker.md) |
| [tenant-isolation](./active/tenant-isolation.md) | Tenant isolation test harness | ro | [tenant-isolation](../designs/active/tenant-isolation.md) |

## WIP — numbered, roadmap-aligned

| ID | Title | Owner | Served by designs |
|---|---|---|---|
| [0029](./wip/0029-prompt-caching.md) | Prompt caching & shared context reuse | ro | [0029](../designs/wip/0029-prompt-caching.md) |
| [0030](./wip/0030-model-tier-routing.md) | Model tier routing | ro | [0030](../designs/wip/0030-model-tier-routing.md) |
| [0031](./wip/0031-token-budgets.md) | Per-project token budgets & cost gates | ro | [0031](../designs/wip/0031-token-budgets.md) |
| [0032](./wip/0032-cost-regression-alerts.md) | Prompt & cost regression alerts | ro | [0032](../designs/wip/0032-cost-regression-alerts.md) |
| [0038](./wip/0038-secret-rotation.md) | Automated secret rotation | ro | [0038](../designs/wip/0038-secret-rotation.md) |
| [0040](./wip/0040-confidence-auto-approve.md) | Confidence-scored auto-approval | ro | [0040](../designs/wip/0040-confidence-auto-approve.md) |
| [0045](./wip/0045-cold-start-ingestion.md) | Cold-start knowledge ingestion | ro | [0045](../designs/wip/0045-cold-start-ingestion.md) |
| [0046](./wip/0046-graph-aware-retrieval.md) | Graph-aware knowledge retrieval | ro | [0046](../designs/wip/0046-graph-aware-retrieval.md) |
| [0047](./wip/0047-template-schema-migration.md) | Template schema migration | ro | [0047](../designs/wip/0047-template-schema-migration.md) |
| [0048](./wip/0048-cross-project-patterns.md) | Cross-project pattern surfacing | ro | [0048](../designs/wip/0048-cross-project-patterns.md) |
| [0049](./wip/0049-mcp-agent-interface.md) | MCP agent interface | ro | [0049](../designs/wip/0049-mcp-agent-interface.md) |
| [0050](./wip/0050-oauth-for-mcp-clients.md) | OAuth 2.1 for MCP clients | ro | [0050](../designs/wip/0050-oauth-for-mcp-clients.md) |
| [0051](./wip/0051-coder-core-modular-monolith.md) | coder-core modular monolith hardening | ro | [0051](../designs/wip/0051-coder-core-modular-monolith.md) |

## Deprecated

_None yet._
