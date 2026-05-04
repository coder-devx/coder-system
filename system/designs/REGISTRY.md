# Designs Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Active — subject-named logical components

Logical components of the Coder system as it exists today.

| Slug | Title | Owner | Implements specs | Decided by |
|---|---|---|---|---|
| [admin-panel](./active/admin-panel.md) | Admin Panel | ro | [admin-panel](../product-specs/active/admin-panel.md) | — |
| [architect-worker](./active/architect-worker.md) | Architect Worker | ro | [architect-worker](../product-specs/active/architect-worker.md) | — |
| [audit-log](./active/audit-log.md) | Audit log | ro | [audit-log](../product-specs/active/audit-log.md) | — |
| [branch-cleanup](./active/branch-cleanup.md) | Branch cleanup | ro | [branch-cleanup](../product-specs/active/branch-cleanup.md) | — |
| [coder-core-modular-monolith](./active/coder-core-modular-monolith.md) | coder-core modular monolith hardening | ro | [delivery-and-infra](../product-specs/active/delivery-and-infra.md) | — |
| [continuous-deployment](./active/continuous-deployment.md) | Continuous Deployment | ro | [continuous-deployment](../product-specs/active/continuous-deployment.md) | — |
| [developer-worker](./active/developer-worker.md) | Developer Worker | ro | [developer-worker](../product-specs/active/developer-worker.md) | — |
| [escalations](./active/escalations.md) | Escalations & on-call routing | ro | [escalations](../product-specs/active/escalations.md) | — |
| [impersonation](./active/impersonation.md) | Impersonation | ro | — | [0006](../adrs/0006-per-role-service-accounts.md) |
| [knowledge-freshness](./active/knowledge-freshness.md) | Knowledge Freshness | ro | [knowledge-freshness](../product-specs/active/knowledge-freshness.md) | [0014](../adrs/0014-freshness-from-declared-affects.md) |
| [knowledge-repo-model](./active/knowledge-repo-model.md) | Knowledge Repo Model | ro | — | [0001](../adrs/0001-knowledge-repo-layout.md), [0002](../adrs/0002-yaml-registries.md), [0003](../adrs/0003-mermaid-for-diagrams.md), [0004](../adrs/0004-agents-md-cross-agent-contract.md), [0008](../adrs/0008-ci-validation-of-knowledge-repo.md) |
| [knowledge-stack](./active/knowledge-stack.md) | Knowledge stack | ro | [knowledge-and-admin](../product-specs/active/knowledge-and-admin.md) | — |
| [knowledge-write-api](./active/knowledge-write-api.md) | Knowledge Write API | ro | [knowledge-api](../product-specs/active/knowledge-api.md) | — |
| [multi-tenancy](./active/multi-tenancy.md) | Multi-tenancy | ro | [multi-tenancy](../product-specs/active/multi-tenancy.md) | [0005](../adrs/0005-multi-tenant-coder-core.md) |
| [observability-and-cost-tracking](./active/observability-and-cost-tracking.md) | Observability and Cost Tracking | ro | [observability](../product-specs/active/observability.md) | — |
| [onboarding](./active/onboarding.md) | Project Onboarding | ro | [onboarding](../product-specs/active/onboarding.md) | — |
| [pipeline-operations](./active/pipeline-operations.md) | Pipeline operations | ro | [pipeline-operations](../product-specs/active/pipeline-operations.md) | — |
| [pm-worker](./active/pm-worker.md) | PM Worker | ro | [pm-worker](../product-specs/active/pm-worker.md) | — |
| [reviewer-worker](./active/reviewer-worker.md) | Reviewer Worker | ro | [reviewer-worker](../product-specs/active/reviewer-worker.md) | — |
| [self-healing](./active/self-healing.md) | Self-healing stuck pipelines | ro | [self-healing](../product-specs/active/self-healing.md) | — |
| [service-accounts](./active/service-accounts.md) | Service Accounts | ro | [service-accounts](../product-specs/active/service-accounts.md) | [0006](../adrs/0006-per-role-service-accounts.md) |
| [system-overview](./active/system-overview.md) | System Overview | ro | — | [0001](../adrs/0001-knowledge-repo-layout.md), [0005](../adrs/0005-multi-tenant-coder-core.md), [0006](../adrs/0006-per-role-service-accounts.md), [0007](../adrs/0007-reviewer-separated-from-pm.md), [0008](../adrs/0008-ci-validation-of-knowledge-repo.md) |
| [team-manager-worker](./active/team-manager-worker.md) | Team Manager Worker | ro | [team-manager-worker](../product-specs/active/team-manager-worker.md) | — |
| [tenancy-and-access](./active/tenancy-and-access.md) | Tenancy & access | ro | [tenancy-and-access](../product-specs/active/tenancy-and-access.md) | — |
| [tenant-isolation](./active/tenant-isolation.md) | Tenant isolation test harness | ro | [tenant-isolation](../product-specs/active/tenant-isolation.md) | — |
| [worker-communication](./active/worker-communication.md) | Worker Communication | ro | [task-orchestration](../product-specs/active/task-orchestration.md) | — |
| [worker-roles](./active/worker-roles.md) | Worker Roles | ro | — | [0006](../adrs/0006-per-role-service-accounts.md), [0007](../adrs/0007-reviewer-separated-from-pm.md) |

## WIP — numbered, roadmap-aligned

| ID | Title | Owner | Implements specs | Decided by |
|---|---|---|---|---|
| [0029](./wip/0029-prompt-caching.md) | Prompt caching & shared context reuse | ro | [0029](../product-specs/wip/0029-prompt-caching.md) | — |
| [0030](./wip/0030-model-tier-routing.md) | Model tier routing | ro | [0030](../product-specs/wip/0030-model-tier-routing.md) | — |
| [0031](./wip/0031-token-budgets.md) | Per-project token budgets & cost gates | ro | [0031](../product-specs/wip/0031-token-budgets.md) | — |
| [0032](./wip/0032-cost-regression-alerts.md) | Prompt & cost regression alerts | ro | [0032](../product-specs/wip/0032-cost-regression-alerts.md) | — |
| [0038](./wip/0038-secret-rotation.md) | Automated secret rotation | ro | [0038](../product-specs/wip/0038-secret-rotation.md) | — |
| [0040](./wip/0040-confidence-auto-approve.md) | Confidence-scored auto-approval | ro | [0040](../product-specs/wip/0040-confidence-auto-approve.md) | — |
| [0045](./wip/0045-cold-start-ingestion.md) | Cold-start knowledge ingestion | ro | [0045](../product-specs/wip/0045-cold-start-ingestion.md) | — |
| [0046](./wip/0046-graph-aware-retrieval.md) | Graph-aware knowledge retrieval | ro | [0046](../product-specs/wip/0046-graph-aware-retrieval.md) | — |
| [0047](./wip/0047-template-schema-migration.md) | Template schema migration | ro | [0047](../product-specs/wip/0047-template-schema-migration.md) | [0019](../adrs/0019-alias-tolerance-fleet-completion-gate.md), [0020](../adrs/0020-worker-dispatched-migration-runner.md), [0021](../adrs/0021-deprecate-then-remove-two-migrations.md) |
| [0048](./wip/0048-cross-project-patterns.md) | Cross-project pattern surfacing | ro | [0048](../product-specs/wip/0048-cross-project-patterns.md) | [0022](../adrs/0022-structural-jaccard-for-pattern-discovery.md), [0023](../adrs/0023-admin-api-and-consult-endpoint-as-pattern-surfaces.md), [0024](../adrs/0024-share-patterns-column-as-enforcement-boundary.md) |
| [0049](./wip/0049-mcp-agent-interface.md) | MCP agent interface | ro | [0049](../product-specs/wip/0049-mcp-agent-interface.md) | — |
| [0050](./wip/0050-oauth-for-mcp-clients.md) | OAuth 2.1 for MCP clients | ro | [0050](../product-specs/wip/0050-oauth-for-mcp-clients.md) | — |
| [0052](./wip/0052-managed-repo-action-distribution.md) | Managed-repo GitHub Action distribution | ro | [0052](../product-specs/wip/0052-managed-repo-action-distribution.md) | — |
| [0053](./wip/0053-post-pr-ci-fix-loop.md) | Post-PR CI fix loop | ro | [0053](../product-specs/wip/0053-post-pr-ci-fix-loop.md) | [0017](../adrs/0017-ci-fixup-one-per-sha.md) |
| [0054](./wip/0054-orchestrator-github-state-reconciliation.md) | Orchestrator GitHub-state reconciliation | ro | [0054](../product-specs/wip/0054-orchestrator-github-state-reconciliation.md) | — |
| [0056](./wip/0056-worker-dispatch-durability.md) | Worker dispatch durability — move worker subprocesses out of the HTTP service | ro | [0056](../product-specs/wip/0056-worker-dispatch-durability.md) | — |
| [0057](./wip/0057-role-prompt-knowledge-layout.md) | Role prompt knowledge layout — move per-role and per-mode worker prompts into the knowledge repo | ro | — | — |
| [0066](./wip/0066-navigation-tree-pattern.md) | Navigation tree pattern for specs, designs, and ADRs | ro | — | — |
| [0067](./wip/0067-enable-stuck-pipeline-slack-paging-at-15-minute-threshold.md) | Enable stuck-pipeline Slack paging at 15-minute threshold | ro | — | — |

## Deprecated

| ID | Title | Deprecated at | Reason |
|---|---|---|---|
| [0002](./deprecated/0002-competitive-intelligence-pipeline.md) | Competitive Intelligence Pipeline | — | — |
