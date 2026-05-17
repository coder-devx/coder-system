# Designs Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Active — subject-named logical components

Logical components of the Coder system as it exists today.

| Slug | Title | Owner | Implements specs | Decided by |
|---|---|---|---|---|
| [admin-panel](./active/knowledge/admin-panel.md) | Admin Panel | ro | [admin-panel](../product-specs/active/admin-panel.md) | — |
| [architect-worker](./active/workers/architect-worker.md) | Architect Worker | ro | [architect-worker](../product-specs/active/architect-worker.md) | — |
| [audit-log](./active/tenancy/audit-log.md) | Audit log | ro | [audit-log](../product-specs/active/audit-log.md) | — |
| [automated-secret-rotation](./active/tenancy/automated-secret-rotation.md) | Automated secret rotation | ro | — | — |
| [branch-cleanup](./active/pipeline/branch-cleanup.md) | Branch cleanup | ro | [branch-cleanup](../product-specs/active/branch-cleanup.md) | — |
| [coder-core-modular-monolith](./active/delivery/coder-core-modular-monolith.md) | coder-core modular monolith hardening | ro | [delivery-and-infra](../product-specs/active/delivery-and-infra.md) | — |
| [cold-start-ingestion](./active/knowledge/cold-start-ingestion.md) | Cold-start knowledge ingestion | ro | — | — |
| [confidence-auto-approval](./active/pipeline/confidence-auto-approval.md) | Confidence-scored auto-approval | ro | — | — |
| [continuous-deployment](./active/delivery/continuous-deployment.md) | Continuous Deployment | ro | [continuous-deployment](../product-specs/active/continuous-deployment.md) | — |
| [cost-regression-alerts](./active/pipeline/cost-regression-alerts.md) | Prompt & cost regression alerts | ro | — | — |
| [cross-project-patterns](./active/knowledge/cross-project-patterns.md) | Cross-project pattern surfacing | ro | — | [0022](../adrs/0022-structural-jaccard-for-pattern-discovery.md), [0023](../adrs/0023-admin-api-and-consult-endpoint-as-pattern-surfaces.md), [0024](../adrs/0024-share-patterns-column-as-enforcement-boundary.md) |
| [delivery-and-infra](./active/delivery-and-infra.md) | Delivery & infra | ro | [delivery-and-infra](../product-specs/active/delivery-and-infra.md) | — |
| [developer-worker](./active/workers/developer-worker.md) | Developer Worker | ro | [developer-worker](../product-specs/active/developer-worker.md) | — |
| [dispatcher](./active/pipeline/dispatcher.md) | Task dispatcher | ro | [pipeline-operations](../product-specs/active/pipeline-operations.md) | — |
| [escalations](./active/pipeline/escalations.md) | Escalations & on-call routing | ro | [escalations](../product-specs/active/escalations.md) | — |
| [graph-aware-retrieval](./active/knowledge/graph-aware-retrieval.md) | Graph-aware knowledge retrieval | ro | — | — |
| [impersonation](./active/tenancy/impersonation.md) | Impersonation | ro | — | [0006](../adrs/0006-per-role-service-accounts.md) |
| [knowledge-and-admin](./active/knowledge-and-admin.md) | Knowledge & admin | ro | [knowledge-and-admin](../product-specs/active/knowledge-and-admin.md) | — |
| [knowledge-freshness](./active/knowledge/knowledge-freshness.md) | Knowledge Freshness | ro | [knowledge-freshness](../product-specs/active/knowledge-freshness.md) | [0014](../adrs/0014-freshness-from-declared-affects.md) |
| [knowledge-repo-model](./active/knowledge/knowledge-repo-model.md) | Knowledge Repo Model | ro | — | [0001](../adrs/0001-knowledge-repo-layout.md), [0002](../adrs/0002-yaml-registries.md), [0003](../adrs/0003-mermaid-for-diagrams.md), [0004](../adrs/0004-agents-md-cross-agent-contract.md), [0008](../adrs/0008-ci-validation-of-knowledge-repo.md) |
| [knowledge-stack](./active/knowledge/knowledge-stack.md) | Knowledge stack | ro | [knowledge-and-admin](../product-specs/active/knowledge-and-admin.md) | — |
| [knowledge-write-api](./active/knowledge/knowledge-write-api.md) | Knowledge Write API | ro | [knowledge-api](../product-specs/active/knowledge-api.md) | — |
| [managed-repo-action-distribution](./active/knowledge/managed-repo-action-distribution.md) | Managed-repo GitHub Action distribution | ro | — | [0018](../adrs/0018-managed-workflows-divergent-file-policy.md) |
| [mcp-agent-interface-design](./active/knowledge/mcp-agent-interface-design.md) | MCP agent interface — let external agents connect, impersonate, and drive Coder | ro | — | — |
| [model-tier-routing](./active/pipeline/model-tier-routing.md) | Model tier routing | ro | — | — |
| [multi-tenancy](./active/tenancy/multi-tenancy.md) | Multi-tenancy | ro | [multi-tenancy](../product-specs/active/multi-tenancy.md) | [0005](../adrs/0005-multi-tenant-coder-core.md) |
| [navigation-tree-pattern](./active/knowledge/navigation-tree-pattern.md) | Navigation tree pattern for specs, designs, and ADRs | ro | — | — |
| [oauth-mcp-clients](./active/tenancy/oauth-mcp-clients.md) | OAuth 2.1 for MCP clients — auth-code+PKCE+DCR over Google as upstream IdP | ro | — | — |
| [observability-and-cost-tracking](./active/pipeline/observability-and-cost-tracking.md) | Observability and Cost Tracking | ro | [observability](../product-specs/active/observability.md) | — |
| [onboarding](./active/knowledge/onboarding.md) | Project Onboarding | ro | [onboarding](../product-specs/active/onboarding.md) | — |
| [orchestrator-github-state-reconciliation](./active/pipeline/orchestrator-github-state-reconciliation.md) | Orchestrator GitHub-state reconciliation | ro | — | [0016](../adrs/0016-bot-identity-via-user-type.md) |
| [pipeline-operations](./active/pipeline-operations.md) | Pipeline operations | ro | [pipeline-operations](../product-specs/active/pipeline-operations.md) | — |
| [pm-worker](./active/workers/pm-worker.md) | PM Worker | ro | [pm-worker](../product-specs/active/pm-worker.md) | — |
| [post-pr-ci-fix-loop](./active/pipeline/post-pr-ci-fix-loop.md) | Post-PR CI fix loop | ro | — | [0017](../adrs/0017-ci-fixup-one-per-sha.md) |
| [prompt-caching-architecture](./active/pipeline/prompt-caching-architecture.md) | Prompt caching & shared context reuse | ro | — | — |
| [reviewer-worker](./active/workers/reviewer-worker.md) | Reviewer Worker | ro | [reviewer-worker](../product-specs/active/reviewer-worker.md) | — |
| [role-prompt-knowledge-layout](./active/workers/role-prompt-knowledge-layout.md) | Role prompt knowledge layout — move per-role and per-mode worker prompts into the knowledge repo | ro | — | — |
| [self-healing](./active/pipeline/self-healing.md) | Self-healing stuck pipelines | ro | [self-healing](../product-specs/active/self-healing.md) | — |
| [service-accounts](./active/tenancy/service-accounts.md) | Service Accounts | ro | [service-accounts](../product-specs/active/service-accounts.md) | [0006](../adrs/0006-per-role-service-accounts.md) |
| [stuck-pipeline-slack-paging](./active/pipeline/stuck-pipeline-slack-paging.md) | Enable stuck-pipeline Slack paging at 15-minute threshold | ro | — | — |
| [system-overview](./active/system-overview.md) | System Overview | ro | — | [0001](../adrs/0001-knowledge-repo-layout.md), [0005](../adrs/0005-multi-tenant-coder-core.md), [0006](../adrs/0006-per-role-service-accounts.md), [0007](../adrs/0007-reviewer-separated-from-pm.md), [0008](../adrs/0008-ci-validation-of-knowledge-repo.md) |
| [task-lifecycle](./active/pipeline/task-lifecycle.md) | Task lifecycle and overrides | ro | [pipeline-operations](../product-specs/active/pipeline-operations.md) | — |
| [team-manager-worker](./active/workers/team-manager-worker.md) | Team Manager Worker | ro | [team-manager-worker](../product-specs/active/team-manager-worker.md) | — |
| [template-schema-migration](./active/knowledge/template-schema-migration.md) | Template schema migration | ro | — | [0019](../adrs/0019-alias-tolerance-fleet-completion-gate.md), [0020](../adrs/0020-worker-dispatched-migration-runner.md), [0021](../adrs/0021-deprecate-then-remove-two-migrations.md) |
| [tenancy-and-access](./active/tenancy-and-access.md) | Tenancy & access | ro | [tenancy-and-access](../product-specs/active/tenancy-and-access.md) | — |
| [tenant-isolation](./active/delivery/tenant-isolation.md) | Tenant isolation test harness | ro | [tenant-isolation](../product-specs/active/tenant-isolation.md) | — |
| [token-budgets-and-cost-gates](./active/pipeline/token-budgets-and-cost-gates.md) | Per-project token budgets & cost gates | ro | — | — |
| [worker-auth-env](./active/workers/worker-auth-env.md) | Worker auth env wiring | ro | [worker-roles](../product-specs/active/worker-roles.md) | — |
| [worker-communication](./active/pipeline/worker-communication.md) | Worker Communication | ro | [task-orchestration](../product-specs/active/task-orchestration.md) | — |
| [worker-dispatch-durability](./active/pipeline/worker-dispatch-durability.md) | Worker dispatch durability — move worker subprocesses out of the HTTP service | ro | — | — |
| [worker-roles](./active/worker-roles.md) | Worker Roles | ro | — | [0006](../adrs/0006-per-role-service-accounts.md), [0007](../adrs/0007-reviewer-separated-from-pm.md) |

## WIP — numbered, roadmap-aligned

| ID | Title | Owner | Implements specs | Decided by |
|---|---|---|---|---|
| [0069](./wip/0069-canonical-project-state.md) | Canonical project-state endpoint and consumers | ro | [0069](../product-specs/wip/0069-canonical-project-state.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0070](./wip/0070-now-landing-surface.md) | Now — operator's actionable queue as default landing | ro | [0070](../product-specs/wip/0070-now-landing-surface.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0071](./wip/0071-failure-mode-grouping-and-runbooks.md) | Failure-mode grouping and operator runbooks | ro | [0071](../product-specs/wip/0071-failure-mode-grouping-and-runbooks.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0072](./wip/0072-task-replay-and-diagnostics.md) | Task replay and diagnostic surface | ro | [0072](../product-specs/wip/0072-task-replay-and-diagnostics.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0073](./wip/0073-drive-mode-in-browser.md) | Drive mode — operator role takeover in the browser | ro | [0073](../product-specs/wip/0073-drive-mode-in-browser.md) | [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md) |
| [0075](./wip/0075-studio-architecture.md) | Studio Architecture | ro | — | — |
| [0077](./wip/0077-coder-studio-founder-role-phase-a.md) | Coder Studio — Founder Role Phase A | ro | — | — |
| [0079](./wip/0079-coder-product-template-repo-contract.md) | Coder Product Template Repo Contract | ro | — | — |
| [0080](./wip/0080-studio-stripe-posthog-integration.md) | Studio Stripe Connect and PostHog Integration | ro | — | — |
| [0081](./wip/0081-dispatcher-re-kick-for-tasks-stuck-at-queued-executing.md) | Dispatcher re-kick for tasks stuck at queued/executing | ro | — | — |
| [0082](./wip/0082-alembic-head-conflict-detection-and-deploy-migrate-paging.md) | Alembic Head-Conflict Detection and Deploy-Migrate Paging | ro | — | — |
| [0083](./wip/0083-plan-unblock-retry-chain-awareness.md) | Plan-unblock retry-chain awareness | ro | — | — |
| [0084](./wip/0084-worker-pr-url-guard-against-duplicate-prs-on-retry.md) | Worker PR-URL Guard Against Duplicate PRs on Retry | ro | — | — |
| [0085](./wip/0085-adr-id-allocation-race-claim-on-dispatch.md) | ADR ID Allocation Race — Claim-on-Dispatch | ro | — | — |
| [0086](./wip/0086-adr-collision-failure-kind-tagging.md) | ADR Collision failure_kind Tagging | ro | — | — |
| [0087](./wip/0087-lint-pre-flight-hard-gate.md) | Lint pre-flight hard gate | ro | — | — |
| [0088](./wip/0088-worker-prod-credentials-isolation.md) | Worker Prod-Credentials Isolation | ro | — | — |
| [0089](./wip/0089-branch-protection-enforcement.md) | Branch Protection Enforcement for Orchestrator-Managed Repos | ro | — | — |
| [0090](./wip/0090-deploy-chain-flake-resilience.md) | Deploy-chain flake resilience | ro | — | — |
| [0091](./wip/0091-caplog-inter-test-pollution-bisect-fix-and-harness-regression.md) | Caplog inter-test pollution: bisect, fix, and harness regression | ro | — | — |
| [0092](./wip/0092-pm-retry-via-override.md) | PM retry via override | ro | — | — |
| [0093](./wip/0093-broken-cross-link-failure-detail.md) | broken_cross_link Failure Detail | ro | — | — |
| [0094](./wip/0094-reviewer-security-and-performance-analysis.md) | Reviewer Security and Performance Analysis | ro | — | — |
| [0095](./wip/0095-role-scoped-knowledge-layout-and-cached-workspace-context.md) | Role-Scoped Knowledge Layout and Cached Workspace Context | ro | — | — |

## Deprecated

| ID | Title | Deprecated at | Reason |
|---|---|---|---|
| [competitive-intelligence-pipeline](./deprecated/competitive-intelligence-pipeline.md) | Competitive Intelligence Pipeline | — | — |
