# Designs Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Active — subject-named logical components

Logical components of the Coder system as it exists today.

| Slug | Title | Owner | Implements specs | Decided by |
|---|---|---|---|---|
| [admin-panel](./active/admin-panel.md) | Admin Panel | ro | [admin-panel](../product-specs/active/admin-panel.md) | — |
| [architect-worker](./active/architect-worker.md) | Architect Worker | ro | [architect-worker](../product-specs/active/architect-worker.md) | — |
| [audit-log](./active/audit-log.md) | Audit log | ro | [audit-log](../product-specs/active/audit-log.md) | — |
| [automated-secret-rotation](./active/automated-secret-rotation.md) | Automated secret rotation | ro | — | — |
| [branch-cleanup](./active/branch-cleanup.md) | Branch cleanup | ro | [branch-cleanup](../product-specs/active/branch-cleanup.md) | — |
| [coder-core-modular-monolith](./active/coder-core-modular-monolith.md) | coder-core modular monolith hardening | ro | [delivery-and-infra](../product-specs/active/delivery-and-infra.md) | — |
| [cold-start-ingestion](./active/cold-start-ingestion.md) | Cold-start knowledge ingestion | ro | — | — |
| [confidence-auto-approval](./active/confidence-auto-approval.md) | Confidence-scored auto-approval | ro | — | — |
| [continuous-deployment](./active/continuous-deployment.md) | Continuous Deployment | ro | [continuous-deployment](../product-specs/active/continuous-deployment.md) | — |
| [cost-regression-alerts](./active/cost-regression-alerts.md) | Prompt & cost regression alerts | ro | — | — |
| [cross-project-patterns](./active/cross-project-patterns.md) | Cross-project pattern surfacing | ro | — | [0022](../adrs/0022-structural-jaccard-for-pattern-discovery.md), [0023](../adrs/0023-admin-api-and-consult-endpoint-as-pattern-surfaces.md), [0024](../adrs/0024-share-patterns-column-as-enforcement-boundary.md) |
| [developer-worker](./active/developer-worker.md) | Developer Worker | ro | [developer-worker](../product-specs/active/developer-worker.md) | — |
| [escalations](./active/escalations.md) | Escalations & on-call routing | ro | [escalations](../product-specs/active/escalations.md) | — |
| [graph-aware-retrieval](./active/graph-aware-retrieval.md) | Graph-aware knowledge retrieval | ro | — | — |
| [impersonation](./active/impersonation.md) | Impersonation | ro | — | [0006](../adrs/0006-per-role-service-accounts.md) |
| [knowledge-freshness](./active/knowledge-freshness.md) | Knowledge Freshness | ro | [knowledge-freshness](../product-specs/active/knowledge-freshness.md) | [0014](../adrs/0014-freshness-from-declared-affects.md) |
| [knowledge-repo-model](./active/knowledge-repo-model.md) | Knowledge Repo Model | ro | — | [0001](../adrs/0001-knowledge-repo-layout.md), [0002](../adrs/0002-yaml-registries.md), [0003](../adrs/0003-mermaid-for-diagrams.md), [0004](../adrs/0004-agents-md-cross-agent-contract.md), [0008](../adrs/0008-ci-validation-of-knowledge-repo.md) |
| [knowledge-stack](./active/knowledge-stack.md) | Knowledge stack | ro | [knowledge-and-admin](../product-specs/active/knowledge-and-admin.md) | — |
| [knowledge-write-api](./active/knowledge-write-api.md) | Knowledge Write API | ro | [knowledge-api](../product-specs/active/knowledge-api.md) | — |
| [managed-repo-action-distribution](./active/managed-repo-action-distribution.md) | Managed-repo GitHub Action distribution | ro | — | [0018](../adrs/0018-managed-workflows-divergent-file-policy.md) |
| [mcp-agent-interface-design](./active/mcp-agent-interface-design.md) | MCP agent interface — let external agents connect, impersonate, and drive Coder | ro | — | — |
| [model-tier-routing](./active/model-tier-routing.md) | Model tier routing | ro | — | — |
| [multi-tenancy](./active/multi-tenancy.md) | Multi-tenancy | ro | [multi-tenancy](../product-specs/active/multi-tenancy.md) | [0005](../adrs/0005-multi-tenant-coder-core.md) |
| [navigation-tree-pattern](./active/navigation-tree-pattern.md) | Navigation tree pattern for specs, designs, and ADRs | ro | — | — |
| [oauth-mcp-clients](./active/oauth-mcp-clients.md) | OAuth 2.1 for MCP clients — auth-code+PKCE+DCR over Google as upstream IdP | ro | — | — |
| [observability-and-cost-tracking](./active/observability-and-cost-tracking.md) | Observability and Cost Tracking | ro | [observability](../product-specs/active/observability.md) | — |
| [onboarding](./active/onboarding.md) | Project Onboarding | ro | [onboarding](../product-specs/active/onboarding.md) | — |
| [orchestrator-github-state-reconciliation](./active/orchestrator-github-state-reconciliation.md) | Orchestrator GitHub-state reconciliation | ro | — | [0016](../adrs/0016-bot-identity-via-user-type.md) |
| [pipeline-operations](./active/pipeline-operations.md) | Pipeline operations | ro | [pipeline-operations](../product-specs/active/pipeline-operations.md) | — |
| [pm-worker](./active/pm-worker.md) | PM Worker | ro | [pm-worker](../product-specs/active/pm-worker.md) | — |
| [post-pr-ci-fix-loop](./active/post-pr-ci-fix-loop.md) | Post-PR CI fix loop | ro | — | [0017](../adrs/0017-ci-fixup-one-per-sha.md) |
| [prompt-caching-architecture](./active/prompt-caching-architecture.md) | Prompt caching & shared context reuse | ro | — | — |
| [reviewer-worker](./active/reviewer-worker.md) | Reviewer Worker | ro | [reviewer-worker](../product-specs/active/reviewer-worker.md) | — |
| [role-prompt-knowledge-layout](./active/role-prompt-knowledge-layout.md) | Role prompt knowledge layout — move per-role and per-mode worker prompts into the knowledge repo | ro | — | — |
| [self-healing](./active/self-healing.md) | Self-healing stuck pipelines | ro | [self-healing](../product-specs/active/self-healing.md) | — |
| [service-accounts](./active/service-accounts.md) | Service Accounts | ro | [service-accounts](../product-specs/active/service-accounts.md) | [0006](../adrs/0006-per-role-service-accounts.md) |
| [stuck-pipeline-slack-paging](./active/stuck-pipeline-slack-paging.md) | Enable stuck-pipeline Slack paging at 15-minute threshold | ro | — | — |
| [system-overview](./active/system-overview.md) | System Overview | ro | — | [0001](../adrs/0001-knowledge-repo-layout.md), [0005](../adrs/0005-multi-tenant-coder-core.md), [0006](../adrs/0006-per-role-service-accounts.md), [0007](../adrs/0007-reviewer-separated-from-pm.md), [0008](../adrs/0008-ci-validation-of-knowledge-repo.md) |
| [team-manager-worker](./active/team-manager-worker.md) | Team Manager Worker | ro | [team-manager-worker](../product-specs/active/team-manager-worker.md) | — |
| [template-schema-migration](./active/template-schema-migration.md) | Template schema migration | ro | — | [0019](../adrs/0019-alias-tolerance-fleet-completion-gate.md), [0020](../adrs/0020-worker-dispatched-migration-runner.md), [0021](../adrs/0021-deprecate-then-remove-two-migrations.md) |
| [tenancy-and-access](./active/tenancy-and-access.md) | Tenancy & access | ro | [tenancy-and-access](../product-specs/active/tenancy-and-access.md) | — |
| [tenant-isolation](./active/tenant-isolation.md) | Tenant isolation test harness | ro | [tenant-isolation](../product-specs/active/tenant-isolation.md) | — |
| [token-budgets-and-cost-gates](./active/token-budgets-and-cost-gates.md) | Per-project token budgets & cost gates | ro | — | — |
| [worker-communication](./active/worker-communication.md) | Worker Communication | ro | [task-orchestration](../product-specs/active/task-orchestration.md) | — |
| [worker-dispatch-durability](./active/worker-dispatch-durability.md) | Worker dispatch durability — move worker subprocesses out of the HTTP service | ro | — | — |
| [worker-roles](./active/worker-roles.md) | Worker Roles | ro | — | [0006](../adrs/0006-per-role-service-accounts.md), [0007](../adrs/0007-reviewer-separated-from-pm.md) |

## WIP — numbered, roadmap-aligned

| ID | Title | Owner | Implements specs | Decided by |
|---|---|---|---|---|
| [0069](./wip/0069-canonical-project-state.md) | Canonical project-state endpoint and consumers | ro | [0069](../product-specs/wip/0069-canonical-project-state.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0070](./wip/0070-now-landing-surface.md) | Now — operator's actionable queue as default landing | ro | [0070](../product-specs/wip/0070-now-landing-surface.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0071](./wip/0071-failure-mode-grouping-and-runbooks.md) | Failure-mode grouping and operator runbooks | ro | [0071](../product-specs/wip/0071-failure-mode-grouping-and-runbooks.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0072](./wip/0072-task-replay-and-diagnostics.md) | Task replay and diagnostic surface | ro | [0072](../product-specs/wip/0072-task-replay-and-diagnostics.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0073](./wip/0073-drive-mode-in-browser.md) | Drive mode — operator role takeover in the browser | ro | [0073](../product-specs/wip/0073-drive-mode-in-browser.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |

## Deprecated

| ID | Title | Deprecated at | Reason |
|---|---|---|---|
| [competitive-intelligence-pipeline](./deprecated/competitive-intelligence-pipeline.md) | Competitive Intelligence Pipeline | — | — |
