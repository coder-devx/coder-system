# Coder system — index

> Generated from `product-specs/registry.yaml` + `designs/registry.yaml` and the `parent:` / `summary:` frontmatter on each active artifact (ADR 0029). Hand edits are lost on the next `scripts/render_index.py` run.

Workers (PM, Architect, Reviewer, Team Manager) and humans should start here when grounding on the existing system. WIPs and deprecated artifacts are not listed — see `registry.yaml` for the full set and `ROADMAP.md` for in-flight work.

## System Overview

Big-picture engineering view of the Coder system.

- Design: [system-overview](./designs/active/system-overview.md)

## Pipeline operations

How tasks flow reliably through a project's pipeline, stay observable, and recover when stalled.

- Spec: [pipeline-operations](./product-specs/active/pipeline-operations.md)
- Design: [pipeline-operations](./designs/active/pipeline-operations.md)

- [branch-cleanup](./product-specs/active/pipeline/branch-cleanup.md) (spec) · [branch-cleanup](./designs/active/pipeline/branch-cleanup.md) (design) — Automatic GC of stale Developer feature branches.
- [confidence-auto-approval](./designs/active/pipeline/confidence-auto-approval.md) (design) — Confidence-scored auto-approval for low-risk worker outputs.
- [cost-regression-alerts](./designs/active/pipeline/cost-regression-alerts.md) (design) — Alerts for prompt and per-task cost regressions.
- [dispatcher](./designs/active/pipeline/dispatcher.md) (design) — Per-project fair-scheduled task dispatcher; SKIP LOCKED lease + Cloud Run Job execution.
- [escalations](./product-specs/active/pipeline/escalations.md) (spec) · [escalations](./designs/active/pipeline/escalations.md) (design) — Three-rung on-call ladder with quiet hours.
- [model-tier-routing](./designs/active/pipeline/model-tier-routing.md) (design) — Route tasks to model tiers (Opus / Sonnet / Haiku) by complexity and cost.
- [observability](./product-specs/active/pipeline/observability.md) (spec) — Per-task telemetry, token costs, and pipeline metrics.
- [observability-and-cost-tracking](./designs/active/pipeline/observability-and-cost-tracking.md) (design) — Telemetry, cost accounting, and alerts for the running pipeline.
- [orchestrator-github-state-reconciliation](./designs/active/pipeline/orchestrator-github-state-reconciliation.md) (design) — Reconcile pipeline state with GitHub PR state.
- [post-pr-ci-fix-loop](./designs/active/pipeline/post-pr-ci-fix-loop.md) (design) — Bounded CI-failure fix loop after Developer PRs land.
- [prompt-caching-architecture](./designs/active/pipeline/prompt-caching-architecture.md) (design) — Prompt caching and shared-context reuse across workers.
- [self-healing](./product-specs/active/pipeline/self-healing.md) (spec) · [self-healing](./designs/active/pipeline/self-healing.md) (design) — Reaper for stuck tasks past timeout.
- [stuck-pipeline-slack-paging](./designs/active/pipeline/stuck-pipeline-slack-paging.md) (design) — Page Slack at the 15-minute stuck-pipeline threshold.
- [task-lifecycle](./designs/active/pipeline/task-lifecycle.md) (design) — Orthogonal status × stage machine; admin override actions (retry / resume / skip_to_stage / pause / reject).
- [task-orchestration](./product-specs/active/pipeline/task-orchestration.md) (spec) — Task lifecycle, dispatcher, and stage transitions.
- [token-budgets-and-cost-gates](./designs/active/pipeline/token-budgets-and-cost-gates.md) (design) — Per-project monthly token budgets enforced by pre-dispatch gate + post-completion rollup.
- [worker-communication](./designs/active/pipeline/worker-communication.md) (design) — Task-state machine, dispatcher protocol, and SSE streaming.
- [worker-dispatch-durability](./designs/active/pipeline/worker-dispatch-durability.md) (design) — Move worker subprocesses out of the HTTP service for durability.

## Worker roles

The team of role-specialised agents that fill a project's pipeline.

- Spec: [worker-roles](./product-specs/active/worker-roles.md)
- Design: [worker-roles](./designs/active/worker-roles.md)

- [architect-worker](./product-specs/active/workers/architect-worker.md) (spec) · [architect-worker](./designs/active/workers/architect-worker.md) (design) — Software Architect worker — designs, ADRs, and system shape.
- [developer-worker](./product-specs/active/workers/developer-worker.md) (spec) · [developer-worker](./designs/active/workers/developer-worker.md) (design) — Developer worker — code, tests, PRs.
- [pm-worker](./product-specs/active/workers/pm-worker.md) (spec) · [pm-worker](./designs/active/workers/pm-worker.md) (design) — Product Manager worker — owns specs and acceptance.
- [reviewer-worker](./product-specs/active/workers/reviewer-worker.md) (spec) · [reviewer-worker](./designs/active/workers/reviewer-worker.md) (design) — Reviewer worker — technical-quality gate before PM acceptance.
- [role-prompt-knowledge-layout](./designs/active/workers/role-prompt-knowledge-layout.md) (design) — Per-role and per-mode prompt assembly from the knowledge repo.
- [team-manager-worker](./product-specs/active/workers/team-manager-worker.md) (spec) · [team-manager-worker](./designs/active/workers/team-manager-worker.md) (design) — Team Manager worker — decomposes specs into developer tasks.
- [worker-auth-env](./designs/active/workers/worker-auth-env.md) (design) — Per-task Claude credential resolution + env hygiene; prevents API-key/OAuth-token leakage between modes.

## Tenancy & access

How one Coder deployment serves many projects without crossing wires and attributes every action to a real actor.

- Spec: [tenancy-and-access](./product-specs/active/tenancy-and-access.md)
- Design: [tenancy-and-access](./designs/active/tenancy-and-access.md)

- [audit-log](./product-specs/active/tenancy/audit-log.md) (spec) · [audit-log](./designs/active/tenancy/audit-log.md) (design) — Every mutation recorded with actor, action, before, after.
- [automated-secret-rotation](./designs/active/tenancy/automated-secret-rotation.md) (design) — Scheduled, audited rotation of project secrets.
- [impersonation](./product-specs/active/tenancy/impersonation.md) (spec) · [impersonation](./designs/active/tenancy/impersonation.md) (design) — Short-lived role-scoped bearer tokens for worker actions.
- [mcp-agent-interface](./product-specs/active/tenancy/mcp-agent-interface.md) (spec) — Let external agents connect, impersonate, and drive Coder via MCP.
- [multi-tenancy](./product-specs/active/tenancy/multi-tenancy.md) (spec) · [multi-tenancy](./designs/active/tenancy/multi-tenancy.md) (design) — project_id everywhere invariant — no cross-tenant data access.
- [oauth-mcp](./product-specs/active/tenancy/oauth-mcp.md) (spec) — OAuth 2.1 (auth-code + PKCE + DCR) for MCP clients.
- [oauth-mcp-clients](./designs/active/tenancy/oauth-mcp-clients.md) (design) — OAuth 2.1 (auth-code + PKCE + DCR) for MCP clients over Google as upstream IdP.
- [secret-rotation](./product-specs/active/tenancy/secret-rotation.md) (spec) — Automated, audited rotation of project secrets.
- [service-accounts](./product-specs/active/tenancy/service-accounts.md) (spec) · [service-accounts](./designs/active/tenancy/service-accounts.md) (design) — Per-role GCP service accounts and brokered escalations.

## Knowledge & admin

How a project's knowledge is read, written, kept current, and surfaced to operators.

- Spec: [knowledge-and-admin](./product-specs/active/knowledge-and-admin.md)
- Design: [knowledge-and-admin](./designs/active/knowledge-and-admin.md)

- [admin-panel](./product-specs/active/knowledge/admin-panel.md) (spec) · [admin-panel](./designs/active/knowledge/admin-panel.md) (design) — User-facing SPA for status, debug, override.
- [cold-start-ingestion](./product-specs/active/knowledge/cold-start-ingestion.md) (spec) · [cold-start-ingestion](./designs/active/knowledge/cold-start-ingestion.md) (design) — Bootstrap a new project's knowledge from existing repos.
- [cross-project-patterns](./designs/active/knowledge/cross-project-patterns.md) (design) — Surface recurring failure patterns across projects.
- [fleet-patterns](./product-specs/active/knowledge/fleet-patterns.md) (spec) — Surface recurring failure patterns across managed projects.
- [graph-aware-retrieval](./designs/active/knowledge/graph-aware-retrieval.md) (design) — Graph-walking retrieval over knowledge cross-links.
- [knowledge-api](./product-specs/active/knowledge/knowledge-api.md) (spec) — Read-through layer over the knowledge repo with per-project cache.
- [knowledge-freshness](./product-specs/active/knowledge/knowledge-freshness.md) (spec) · [knowledge-freshness](./designs/active/knowledge/knowledge-freshness.md) (design) — Automatic stale-artifact detection and rewrites.
- [knowledge-schema-migration](./product-specs/active/knowledge/knowledge-schema-migration.md) (spec) — Migrate managed-project knowledge repos when the template schema changes.
- [knowledge-stack](./designs/active/knowledge/knowledge-stack.md) (design) — How each project's knowledge repo is served, written, and kept fresh.
  - [knowledge-repo-model](./designs/active/knowledge/knowledge-repo-model.md) (design) — Knowledge repo shape and the typed-artifact contract.
    - [navigation-tree-pattern](./designs/active/knowledge/navigation-tree-pattern.md) (design) — Hierarchical category tree pattern, generated into system/INDEX.md.
  - [knowledge-write-api](./designs/active/knowledge/knowledge-write-api.md) (design) — HTTP write surface for the knowledge repo.
- [managed-repo-action-distribution](./designs/active/knowledge/managed-repo-action-distribution.md) (design) — Distribute and verify managed GitHub Actions across the fleet.
- [managed-workflows](./product-specs/active/knowledge/managed-workflows.md) (spec) — Distribute and version managed GitHub Actions across the fleet.
- [mcp-agent-interface-design](./designs/active/knowledge/mcp-agent-interface-design.md) (design) — MCP surface — let external agents connect, impersonate, and drive Coder.
- [onboarding](./product-specs/active/knowledge/onboarding.md) (spec) · [onboarding](./designs/active/knowledge/onboarding.md) (design) — How a new project gets wired into Coder.
- [template-schema-migration](./designs/active/knowledge/template-schema-migration.md) (design) — Migrate managed-project knowledge repos when the template schema changes.

## Delivery & infra

How code reaches production and how the system itself stays maintainable.

- Spec: [delivery-and-infra](./product-specs/active/delivery-and-infra.md)
- Design: [delivery-and-infra](./designs/active/delivery-and-infra.md)

- [coder-core-modular-monolith](./designs/active/delivery/coder-core-modular-monolith.md) (design) — Layered import contracts (adapters → services → domain), enforced by import-linter.
- [continuous-deployment](./product-specs/active/delivery/continuous-deployment.md) (spec) · [continuous-deployment](./designs/active/delivery/continuous-deployment.md) (design) — Push-to-main CD with health checks.
- [tenant-isolation](./product-specs/active/delivery/tenant-isolation.md) (spec) · [tenant-isolation](./designs/active/delivery/tenant-isolation.md) (design) — Test-suite harness for the multi-tenancy contract.
