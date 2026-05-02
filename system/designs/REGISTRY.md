# Designs Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Active — subject-named logical components

Logical components of the Coder system as it exists today.

| Slug | Title | Owner | Implements specs | Decided by |
|---|---|---|---|---|
| [architect-worker](./active/architect-worker.md) | Architect Worker | ro | [architect-worker](../product-specs/active/architect-worker.md) | — |
| [audit-log](./active/audit-log.md) | Audit log | ro | [audit-log](../product-specs/active/audit-log.md) | — |
| [branch-cleanup](./active/branch-cleanup.md) | Branch cleanup | ro | [branch-cleanup](../product-specs/active/branch-cleanup.md) | — |
| [escalations](./active/escalations.md) | Escalations & on-call routing | ro | [escalations](../product-specs/active/escalations.md) | — |
| [impersonation](./active/impersonation.md) | Impersonation | ro | — | [0006](../adrs/0006-per-role-service-accounts.md) |
| [knowledge-freshness](./active/knowledge-freshness.md) | Knowledge Freshness | ro | [knowledge-freshness](../product-specs/active/knowledge-freshness.md) | [0014](../adrs/0014-freshness-from-declared-affects.md) |
| [knowledge-repo-model](./active/knowledge-repo-model.md) | Knowledge Repo Model | ro | — | 0001, 0002, 0003, 0004, 0008 |
| [knowledge-write-api](./active/knowledge-write-api.md) | Knowledge Write API | ro | [knowledge-api](../product-specs/active/knowledge-api.md) | — |
| [observability-and-cost-tracking](./active/observability-and-cost-tracking.md) | Observability and Cost Tracking | ro | [observability](../product-specs/active/observability.md) | — |
| [pm-worker](./active/pm-worker.md) | PM Worker | ro | [pm-worker](../product-specs/active/pm-worker.md) | — |
| [self-healing](./active/self-healing.md) | Self-healing stuck pipelines | ro | [self-healing](../product-specs/active/self-healing.md) | — |
| [system-overview](./active/system-overview.md) | System Overview | ro | — | 0001, 0005, 0006, 0007, 0008 |
| [team-manager-worker](./active/team-manager-worker.md) | Team Manager Worker | ro | [team-manager-worker](../product-specs/active/team-manager-worker.md) | — |
| [tenant-isolation](./active/tenant-isolation.md) | Tenant isolation test harness | ro | [tenant-isolation](../product-specs/active/tenant-isolation.md) | — |
| [worker-communication](./active/worker-communication.md) | Worker Communication | ro | [task-orchestration](../product-specs/active/task-orchestration.md) | — |
| [worker-roles](./active/worker-roles.md) | Worker Roles | ro | — | 0006, 0007 |
| [0051-coder-core-modular-monolith](./active/0051-coder-core-modular-monolith.md) | coder-core modular monolith hardening | ro | [0051](../product-specs/active/0051-coder-core-modular-monolith.md) | — |

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
| [0047](./wip/0047-template-schema-migration.md) | Template schema migration | ro | [0047](../product-specs/wip/0047-template-schema-migration.md) | — |
| [0048](./wip/0048-cross-project-patterns.md) | Cross-project pattern surfacing | ro | [0048](../product-specs/wip/0048-cross-project-patterns.md) | — |
| [0049](./wip/0049-mcp-agent-interface.md) | MCP agent interface | ro | [0049](../product-specs/wip/0049-mcp-agent-interface.md) | — |
| [0050](./wip/0050-oauth-for-mcp-clients.md) | OAuth 2.1 for MCP clients | ro | [0050](../product-specs/wip/0050-oauth-for-mcp-clients.md) | — |
| [0052](./wip/0052-managed-repo-action-distribution.md) | Managed-repo GitHub Action distribution | ro | [0052](../product-specs/wip/0052-managed-repo-action-distribution.md) | — |
| [0053](./wip/0053-post-pr-ci-fix-loop.md) | Post-PR CI fix loop | ro | [0053](../product-specs/wip/0053-post-pr-ci-fix-loop.md) | [0017](../adrs/0017-ci-fixup-one-per-sha.md) |
| [0054](./wip/0054-orchestrator-github-state-reconciliation.md) | Orchestrator GitHub-state reconciliation | ro | [0054](../product-specs/wip/0054-orchestrator-github-state-reconciliation.md) | — |
| [0056](./wip/0056-worker-dispatch-durability.md) | Worker dispatch durability — move worker subprocesses out of the HTTP service | ro | [0056](../product-specs/wip/0056-worker-dispatch-durability.md) | — |
| [0057](./wip/0057-role-prompt-knowledge-layout.md) | Role prompt knowledge layout — move per-role and per-mode worker prompts into the knowledge repo | ro | — | — |

## Deprecated

| ID | Title | Deprecated at | Reason |
|---|---|---|---|
| [0002](./deprecated/0002-competitive-intelligence-pipeline.md) | Competitive Intelligence Pipeline | 2026-04-23 | Salvaged placeholder from deleted `coder-agent` repo; no spec authored, no roadmap phase scheduled. Rehydrate with a fresh WIP number if the capability is planned. |
