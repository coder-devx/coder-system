# Product Specs Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Active — subject-named logical components

Components of the Coder system as it exists today. Ship history lives
in each component's `## Evolution` section and in git.

| Slug | Title | Owner | Served by designs |
|---|---|---|---|
| [admin-panel](./active/knowledge/admin-panel.md) | Admin Panel | ro | admin-panel |
| [architect-worker](./active/workers/architect-worker.md) | Architect Worker | ro | architect-worker |
| [audit-log](./active/tenancy/audit-log.md) | Audit log | ro | audit-log |
| [branch-cleanup](./active/pipeline/branch-cleanup.md) | Branch cleanup | ro | branch-cleanup |
| [branch-protection](./active/delivery/branch-protection.md) | Branch protection enforcement | ro | — |
| [coder-core-modular-monolith](./active/delivery/coder-core-modular-monolith.md) | coder-core modular monolith | ro | coder-core-modular-monolith |
| [coder-product-template](./active/knowledge/coder-product-template.md) | Coder Studio — coder-product-template contract | ro | — |
| [coder-studio-founder](./active/knowledge/coder-studio-founder.md) | Coder Studio — Founder Role Phase A | ro | — |
| [cold-start-ingestion](./active/knowledge/cold-start-ingestion.md) | Cold-start knowledge ingestion | ro | — |
| [continuous-deployment](./active/delivery/continuous-deployment.md) | Continuous Deployment | ro | continuous-deployment |
| [delivery-and-infra](./active/delivery-and-infra.md) | Delivery & infra | ro | [system-overview](../designs/active/system-overview.md), 0051 |
| [developer-worker](./active/workers/developer-worker.md) | Developer Worker | ro | developer-worker |
| [escalations](./active/pipeline/escalations.md) | Escalations & on-call routing | ro | escalations |
| [fleet-patterns](./active/knowledge/fleet-patterns.md) | Fleet pattern surfacing | ro | — |
| [impersonation](./active/tenancy/impersonation.md) | Impersonation | ro | impersonation |
| [knowledge-and-admin](./active/knowledge-and-admin.md) | Knowledge & admin | ro | knowledge-repo-model, knowledge-write-api, knowledge-freshness |
| [knowledge-api](./active/knowledge/knowledge-api.md) | Knowledge API | ro | knowledge-write-api, knowledge-repo-model |
| [knowledge-freshness](./active/knowledge/knowledge-freshness.md) | Knowledge Freshness | ro | knowledge-freshness |
| [knowledge-schema-migration](./active/knowledge/knowledge-schema-migration.md) | Knowledge schema migration | ro | — |
| [managed-workflows](./active/knowledge/managed-workflows.md) | Managed-repo workflow distribution | ro | — |
| [mcp-agent-interface](./active/knowledge/mcp-agent-interface.md) | MCP agent interface | ro | mcp-agent-interface-design |
| [multi-tenancy](./active/tenancy/multi-tenancy.md) | Multi-tenancy | ro | multi-tenancy |
| [oauth-mcp](./active/tenancy/oauth-mcp.md) | OAuth 2.1 for MCP clients | ro | 0050 |
| [observability](./active/pipeline/observability.md) | Observability | ro | observability-and-cost-tracking |
| [onboarding](./active/knowledge/onboarding.md) | Onboarding | ro | onboarding |
| [pipeline-operations](./active/pipeline-operations.md) | Pipeline operations | ro | worker-communication, observability-and-cost-tracking, escalations, self-healing, branch-cleanup |
| [pm-worker](./active/workers/pm-worker.md) | PM Worker | ro | pm-worker |
| [reviewer-worker](./active/workers/reviewer-worker.md) | Reviewer Worker | ro | reviewer-worker |
| [secret-rotation](./active/tenancy/secret-rotation.md) | Automated secret rotation | ro | — |
| [self-healing](./active/pipeline/self-healing.md) | Self-healing stuck pipelines | ro | self-healing |
| [service-accounts](./active/tenancy/service-accounts.md) | Service Accounts | ro | service-accounts |
| [spec-lifecycle-coordinator](./active/pipeline/spec-lifecycle-coordinator.md) | Spec-lifecycle coordinator | ro | [0076](../designs/wip/0076-spec-bound-architect-dispatch.md), [0078](../designs/wip/0078-spec-run-lifecycle-auto-bootstrap.md) |
| [studio](./active/knowledge/studio.md) | Studio | ro | — |
| [studio-b2c-portfolio](./active/studio-b2c-portfolio.md) | Studio — B2C product portfolio operator contract | ro | — |
| [studio-product-integrations](./active/knowledge/studio-product-integrations.md) | Studio — Stripe Connect and PostHog integration | ro | — |
| [task-orchestration](./active/pipeline/task-orchestration.md) | Task Orchestration | ro | worker-communication |
| [team-manager-worker](./active/workers/team-manager-worker.md) | Team Manager Worker | ro | team-manager-worker |
| [tenancy-and-access](./active/tenancy-and-access.md) | Tenancy & access | ro | impersonation, audit-log, tenant-isolation |
| [tenant-isolation](./active/delivery/tenant-isolation.md) | Tenant isolation test harness | ro | tenant-isolation |
| [test-harness-reliability](./active/delivery/test-harness-reliability.md) | Test harness reliability | ro | — |
| [worker-roles](./active/worker-roles.md) | Worker roles | ro | [worker-roles](../designs/active/worker-roles.md), architect-worker, pm-worker, team-manager-worker |

## WIP — numbered, roadmap-aligned

| ID | Title | Owner | Served by designs |
|---|---|---|---|
| [0069](./wip/0069-canonical-project-state.md) | Canonical project-state endpoint and consumers | ro | [0069](../designs/wip/0069-canonical-project-state.md) |
| [0070](./wip/0070-now-landing-surface.md) | Now — operator's actionable queue as default landing | ro | [0070](../designs/wip/0070-now-landing-surface.md) |
| [0071](./wip/0071-failure-mode-grouping-and-runbooks.md) | Failure-mode grouping and operator runbooks | ro | [0071](../designs/wip/0071-failure-mode-grouping-and-runbooks.md) |
| [0072](./wip/0072-task-replay-and-diagnostics.md) | Task replay and diagnostic surface | ro | [0072](../designs/wip/0072-task-replay-and-diagnostics.md) |
| [0073](./wip/0073-drive-mode-in-browser.md) | Drive mode — operator role takeover in the browser | ro | [0073](../designs/wip/0073-drive-mode-in-browser.md) |
| [0074](./wip/0074-spec-compose-write-endpoint.md) | SpecCompose write endpoint and draft hand-off to Now | ro | — |
| [0083](./wip/0083-plan-unblock-checks-retry-chain.md) | Plan-unblock check accounts for retry chain, not just original task's stage | ro | — |
| [0090](./wip/0090-deploy-chain-resilience-to-test-flake.md) | Deploy chain must not be hostage to a single flaky test | ro | — |
| [0092](./wip/0092-pm-retry-via-override.md) | PM and other stage=None tasks must be retriable via override | ro | — |
| [0093](./wip/0093-architect-broken-cross-link-recovery.md) | Architect broken_cross_link should surface the specific field/target instead of silent-dropping | ro | — |
| [0095](./wip/0095-cache-and-cost-observability-correctness.md) | Cache-hit and cost-regression observability is wrong or absent | ro | — |
| [0104](./wip/0104-spec-run-cancel-and-deprecation-reconciler.md) | Spec-run cancel verb + auto-cancel on WIP deprecation | ro | — |

## Deprecated

| ID | Title | Reason |
|---|---|---|
| [0097](./deprecated/0097-worker-knowledge-pull-visibility-on-task-detail.md) | Worker knowledge-pull visibility on task detail | — |
| [0098](./deprecated/0098-worker-knowledge-read-log-in-task-detail.md) | Worker Knowledge Read Log in Task Detail | — |
| [0100](./deprecated/0100-worker-knowledge-reads-inline-on-task-detail.md) | Worker knowledge reads inline on task detail | — |
| [0101](./deprecated/0101-task-knowledge-read-trace.md) | Task Knowledge-Read Trace | — |
| [0102](./deprecated/0102-knowledge-read-trace-on-task-detail.md) | Knowledge-read trace on task detail | — |
| [0103](./deprecated/0103-knowledge-reads-panel-on-task-detail.md) | Knowledge reads panel on task detail | — |
