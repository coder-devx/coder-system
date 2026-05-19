# Reviewer — Reading Map

> Per [design 0095](../../designs/wip/0095-role-scoped-knowledge-layout-and-cached-workspace-context.md).
> Routes by the area a PR's diff touches to the design rollup + leaves
> that govern correctness in that area. The designs tree entry is
> [`system/designs/INDEX.md`](../../designs/INDEX.md).

## Always load

- [`designs/active/system-overview.md`](../../designs/active/system-overview.md) — what runs, where
- [`glossary.md`](../../glossary.md) — shared vocabulary
- [`designs/active/multi-tenancy.md`](../../designs/active/tenancy/multi-tenancy.md) — **load every run**; one missed `project_id` scope = cross-tenant leak
- [`adrs/REGISTRY.md`](../../adrs/REGISTRY.md) — decision history; consult when a PR conflicts with a past decision

## Route by topic

Pick by what the PR's diff touches. The reviewer worker already has a
source workspace clone — these files give you the *design* the diff is
supposed to conform to.

| If the PR touches… | Reads to check conformance against |
|---|---|
| **New / changed API endpoint** | **[tenancy-and-access](../../designs/active/tenancy-and-access.md)** → [multi-tenancy](../../designs/active/tenancy/multi-tenancy.md), [tenant-isolation](../../designs/active/delivery/tenant-isolation.md), [audit-log](../../designs/active/tenancy/audit-log.md) |
| **Worker code or dispatcher** | **[pipeline-operations](../../designs/active/pipeline-operations.md)** → [dispatcher](../../designs/active/pipeline/dispatcher.md), [task-lifecycle](../../designs/active/pipeline/task-lifecycle.md), [worker-communication](../../designs/active/pipeline/worker-communication.md), [worker-dispatch-durability](../../designs/active/pipeline/worker-dispatch-durability.md) |
| **Worker auth / env wiring** | **[worker-roles](../../designs/active/worker-roles.md)** → [worker-auth-env](../../designs/active/workers/worker-auth-env.md) |
| **Knowledge API / writes / ship** | **[knowledge-and-admin](../../designs/active/knowledge-and-admin.md)** → [knowledge-write-api](../../designs/active/knowledge/knowledge-write-api.md), [knowledge-repo-model](../../designs/active/knowledge/knowledge-repo-model.md) |
| **Self-healing / escalations / cron jobs** | **[pipeline-operations](../../designs/active/pipeline-operations.md)** § Recovery → [self-healing](../../designs/active/pipeline/self-healing.md), [escalations](../../designs/active/pipeline/escalations.md), [stuck-pipeline-slack-paging](../../designs/active/pipeline/stuck-pipeline-slack-paging.md) |
| **Auth / secrets / impersonation** | **[tenancy-and-access](../../designs/active/tenancy-and-access.md)** → [service-accounts](../../designs/active/tenancy/service-accounts.md), [automated-secret-rotation](../../designs/active/tenancy/automated-secret-rotation.md), [impersonation](../../designs/active/tenancy/impersonation.md), [oauth-mcp-clients](../../designs/active/tenancy/oauth-mcp-clients.md) |
| **Admin panel React / Vite** | **[knowledge-and-admin](../../designs/active/knowledge-and-admin.md)** → [admin-panel](../../designs/active/knowledge/admin-panel.md), [navigation-tree-pattern](../../designs/active/knowledge/navigation-tree-pattern.md) |
| **Cost / observability** | **[pipeline-operations](../../designs/active/pipeline-operations.md)** § Observability → [observability-and-cost-tracking](../../designs/active/pipeline/observability-and-cost-tracking.md), [token-budgets-and-cost-gates](../../designs/active/pipeline/token-budgets-and-cost-gates.md), [cost-regression-alerts](../../designs/active/pipeline/cost-regression-alerts.md) |
| **Prompts / role prompts / knowledge layout** | **[worker-roles](../../designs/active/worker-roles.md)** → [role-prompt-knowledge-layout](../../designs/active/workers/role-prompt-knowledge-layout.md); **[pipeline-operations](../../designs/active/pipeline-operations.md)** → [prompt-caching-architecture](../../designs/active/pipeline/prompt-caching-architecture.md) |

## Security / performance pass (per spec 0094)

Every review runs a structured security + performance pass alongside
correctness. Categories: OWASP top 10 (injection, broken auth, XSS, IDOR,
secmisc, SSRF, crypto, deserialization, outdated deps, logging gaps) +
credential exposure for security; N+1, unbounded pagination, missing
indexes, O(n²)+ complexity for performance. Critical security findings
force `request_changes`. See [design 0094](../../designs/wip/0094-reviewer-security-and-performance-analysis.md)
for the full schema once it lands.

## When to read background / ADRs

When a PR contradicts an active design, check whether an ADR governs the
decision before flagging. ADR registry: [`adrs/REGISTRY.md`](../../adrs/REGISTRY.md).
Particularly load-bearing: [ADR 0007 (reviewer-separated-from-pm)](../../adrs/0007-reviewer-separated-from-pm.md),
[ADR 0014 (affects_services for freshness)](../../adrs/0014-affects-services-and-repos-as-design-frontmatter.md).

## Notes on this file

- Lives at `system/roles/reviewer/INDEX.md`. Loaded by the reviewer
  worker as part of its cached system prompt (per design 0095 phase 5a).
- The reviewer already has a source clone; this map is about *design
  context*, not code access.
- Output contract: `VERDICT: approve` or `VERDICT: request_changes` on
  its own line — see [`tasks/review.md`](./tasks/review.md).
