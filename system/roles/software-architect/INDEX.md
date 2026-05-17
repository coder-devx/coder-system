# Architect — Reading Map

> Per [design 0095](../../designs/wip/0095-role-scoped-knowledge-layout-and-cached-workspace-context.md).
> The architect's knowledge base is `system/designs/active/`. The tree
> entry point is [`system/designs/INDEX.md`](../../designs/INDEX.md);
> this map narrows that tree to the slice the architect uses for
> *design-mode* tasks.

## Always load

- [`designs/INDEX.md`](../../designs/INDEX.md) — designs tree entry; pick the right category from here
- [`designs/active/system-overview.md`](../../designs/active/system-overview.md) — what runs, where
- [`glossary.md`](../../glossary.md) — shared vocabulary
- [`adrs/REGISTRY.md`](../../adrs/REGISTRY.md) — decision history (binary-fresh; consult on conflict)

## Route by topic

For your spec's topic, open the **category rollup** (bolded) as your
first read — it's the smart sub-entry that lists relevant leaves with
one-liners. Then drill into named leaves below. Each leaf ends with
`## Where in code` symbol anchors.

| If the spec touches… | Category → key leaves |
|---|---|
| **Pipeline / dispatch / task lifecycle** | **[pipeline-operations](../../designs/active/pipeline-operations.md)** → [dispatcher](../../designs/active/pipeline/dispatcher.md), [task-lifecycle](../../designs/active/pipeline/task-lifecycle.md), [worker-communication](../../designs/active/pipeline/worker-communication.md), [worker-dispatch-durability](../../designs/active/pipeline/worker-dispatch-durability.md) |
| **Self-healing / escalations / stuck pipelines** | **[pipeline-operations](../../designs/active/pipeline-operations.md)** § Recovery → [self-healing](../../designs/active/pipeline/self-healing.md), [escalations](../../designs/active/pipeline/escalations.md), [stuck-pipeline-slack-paging](../../designs/active/pipeline/stuck-pipeline-slack-paging.md), [post-pr-ci-fix-loop](../../designs/active/pipeline/post-pr-ci-fix-loop.md) |
| **Cost / observability / model routing** | **[pipeline-operations](../../designs/active/pipeline-operations.md)** § Observability → [observability-and-cost-tracking](../../designs/active/pipeline/observability-and-cost-tracking.md), [cost-regression-alerts](../../designs/active/pipeline/cost-regression-alerts.md), [token-budgets-and-cost-gates](../../designs/active/pipeline/token-budgets-and-cost-gates.md), [model-tier-routing](../../designs/active/pipeline/model-tier-routing.md), [prompt-caching-architecture](../../designs/active/pipeline/prompt-caching-architecture.md) |
| **Workers / role contracts / auth / prompts** | **[worker-roles](../../designs/active/worker-roles.md)** → per-role design ([architect](../../designs/active/workers/architect-worker.md) · [pm](../../designs/active/workers/pm-worker.md) · [developer](../../designs/active/workers/developer-worker.md) · [reviewer](../../designs/active/workers/reviewer-worker.md) · [team-manager](../../designs/active/workers/team-manager-worker.md)) + [worker-auth-env](../../designs/active/workers/worker-auth-env.md), [role-prompt-knowledge-layout](../../designs/active/workers/role-prompt-knowledge-layout.md) |
| **Tenancy / ACL / impersonation / audit / secrets** | **[tenancy-and-access](../../designs/active/tenancy-and-access.md)** → [multi-tenancy](../../designs/active/tenancy/multi-tenancy.md), [impersonation](../../designs/active/tenancy/impersonation.md), [audit-log](../../designs/active/tenancy/audit-log.md), [service-accounts](../../designs/active/tenancy/service-accounts.md), [automated-secret-rotation](../../designs/active/tenancy/automated-secret-rotation.md), [oauth-mcp-clients](../../designs/active/tenancy/oauth-mcp-clients.md) |
| **Knowledge API / freshness / MCP / admin panel** | **[knowledge-and-admin](../../designs/active/knowledge-and-admin.md)** → [knowledge-stack](../../designs/active/knowledge/knowledge-stack.md) (sub-rollup), [knowledge-write-api](../../designs/active/knowledge/knowledge-write-api.md), [knowledge-freshness](../../designs/active/knowledge/knowledge-freshness.md), [graph-aware-retrieval](../../designs/active/knowledge/graph-aware-retrieval.md), [mcp-agent-interface-design](../../designs/active/knowledge/mcp-agent-interface-design.md), [admin-panel](../../designs/active/knowledge/admin-panel.md) |
| **CI/CD / module boundaries / isolation harness** | **[delivery-and-infra](../../designs/active/delivery-and-infra.md)** → [continuous-deployment](../../designs/active/delivery/continuous-deployment.md), [coder-core-modular-monolith](../../designs/active/delivery/coder-core-modular-monolith.md), [tenant-isolation](../../designs/active/delivery/tenant-isolation.md) |

## Code grounding

Per [design 0095](../../designs/wip/0095-role-scoped-knowledge-layout-and-cached-workspace-context.md)
phase 4, architect tasks get a multi-repo workspace clone
(`work/repos/coder-core/...`) when `CODER_ARCHITECT_WORKSPACE_ENABLED`
is on. Use local `Read` / `Grep` over the symbols listed in each
active design's `## Where in code` section. Without the flag, fall
back to `gh api` per [`tasks/design.md`](./tasks/design.md).

## Consulting ADRs

Only when designing something that contradicts a prior decision, or
when you need to understand *why* a current shape exists. Registry:
[`adrs/REGISTRY.md`](../../adrs/REGISTRY.md). Default: don't.

## Notes on this file

- Lives at `system/roles/software-architect/INDEX.md`. Loaded by the
  architect worker as part of its cached system prompt (per design 0095
  phase 5a).
- Routes are stable identifiers — when an active design moves or splits,
  this table updates in place.
- A spec author can override topic routing by setting
  `read_first: [path, …]` in the spec frontmatter.
