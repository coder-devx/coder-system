# Coder system — cross-link graph

> Generated from `served_by_designs`, `implements_specs`, `decided_by`, and `related_*` frontmatter on each active artifact. Hand edits are lost on the next `scripts/render_graph.py` run. The taxonomy tree lives in [`INDEX.md`](./INDEX.md); this file shows the **non-tree** relationships.

Mermaid notation: `[spec]` rectangle, `(design)` rounded. Solid `-->` is `served_by_designs` / `implements_specs` (the spec/design pair that realises a contract). Dashed `-.->` is `related_*` (sibling cross-link).

## Pipeline operations

```mermaid
flowchart LR
  n000("design<br/>branch-cleanup")
  n001("design<br/>confidence-auto-approval")
  n002("design<br/>cost-regression-alerts")
  n003("design<br/>dispatcher")
  n004("design<br/>escalations")
  n005("design<br/>model-tier-routing")
  n006("design<br/>observability-and-cost-tracking")
  n007("design<br/>orchestrator-github-state-reconciliation")
  n008("design<br/>pipeline-operations")
  n009("design<br/>post-pr-ci-fix-loop")
  n010("design<br/>prompt-caching-architecture")
  n011("design<br/>self-healing")
  n012("design<br/>stuck-pipeline-slack-paging")
  n013("design<br/>task-lifecycle")
  n014("design<br/>token-budgets-and-cost-gates")
  n015("design<br/>worker-communication")
  n016("design<br/>worker-dispatch-durability")
  n017["spec<br/>branch-cleanup"]
  n018["spec<br/>escalations"]
  n019["spec<br/>observability"]
  n020["spec<br/>pipeline-operations"]
  n021["spec<br/>self-healing"]
  n022["spec<br/>spec-lifecycle-coordinator"]
  n023["spec<br/>task-orchestration"]
  n017 -->|served by| n000
  n000 -.->|related| n015
  n000 -.->|related| n006
  n001 -.->|related| n015
  n001 -.->|related| n006
  n002 -.->|related| n006
  n002 -.->|related| n015
  n002 -.->|related| n010
  n002 -.->|related| n005
  n002 -.->|related| n014
  n020 -->|served by| n003
  n003 -.->|related| n015
  n003 -.->|related| n016
  n003 -.->|related| n008
  n018 -->|served by| n004
  n004 -.->|related| n015
  n004 -.->|related| n006
  n005 -.->|related| n015
  n005 -.->|related| n006
  n005 -.->|related| n010
  n005 -.->|related| n014
  n019 -->|served by| n006
  n007 -.->|related| n015
  n020 -->|served by| n008
  n008 -.->|related| n015
  n008 -.->|related| n006
  n008 -.->|related| n011
  n008 -.->|related| n004
  n008 -.->|related| n000
  n009 -.->|related| n015
  n009 -.->|related| n004
  n010 -.->|related| n015
  n010 -.->|related| n006
  n021 -->|served by| n011
  n011 -.->|related| n015
  n011 -.->|related| n006
  n011 -.->|related| n004
  n012 -.->|related| n004
  n012 -.->|related| n011
  n012 -.->|related| n008
  n020 -->|served by| n013
  n013 -.->|related| n008
  n013 -.->|related| n015
  n013 -.->|related| n003
  n014 -.->|related| n006
  n014 -.->|related| n015
  n014 -.->|related| n005
  n023 -->|served by| n015
  n016 -.->|related| n015
  n016 -.->|related| n011
  n016 -.->|related| n006
  n017 -->|served by| n000
  n017 -.->|related| n023
  n017 -.->|related| n019
  n018 -->|served by| n004
  n018 -.->|related| n023
  n018 -.->|related| n019
  n019 -->|served by| n006
  n019 -.->|related| n017
  n019 -.->|related| n018
  n019 -.->|related| n021
  n019 -.->|related| n023
  n020 -->|served by| n015
  n020 -->|served by| n006
  n020 -->|served by| n004
  n020 -->|served by| n011
  n020 -->|served by| n000
  n020 -.->|related| n017
  n020 -.->|related| n018
  n020 -.->|related| n019
  n020 -.->|related| n021
  n020 -.->|related| n023
  n021 -->|served by| n011
  n021 -.->|related| n023
  n021 -.->|related| n019
  n021 -.->|related| n018
  n022 -.->|related| n023
  n023 -->|served by| n015
  n023 -.->|related| n018
  n023 -.->|related| n019
  n023 -.->|related| n021
```

## Worker roles

```mermaid
flowchart LR
  n000("design<br/>architect-worker")
  n001("design<br/>developer-worker")
  n002("design<br/>pm-worker")
  n003("design<br/>reviewer-worker")
  n004("design<br/>role-prompt-knowledge-layout")
  n005("design<br/>team-manager-worker")
  n006("design<br/>worker-auth-env")
  n007("design<br/>worker-roles")
  n008["spec<br/>architect-worker"]
  n009["spec<br/>developer-worker"]
  n010["spec<br/>pm-worker"]
  n011["spec<br/>reviewer-worker"]
  n012["spec<br/>team-manager-worker"]
  n013["spec<br/>worker-roles"]
  n008 -->|served by| n000
  n000 -.->|related| n005
  n000 -.->|related| n002
  n000 -.->|related| n007
  n009 -->|served by| n001
  n001 -.->|related| n007
  n001 -.->|related| n002
  n001 -.->|related| n000
  n001 -.->|related| n005
  n010 -->|served by| n002
  n002 -.->|related| n005
  n002 -.->|related| n007
  n011 -->|served by| n003
  n003 -.->|related| n007
  n003 -.->|related| n001
  n004 -.->|related| n007
  n004 -.->|related| n002
  n004 -.->|related| n000
  n004 -.->|related| n005
  n012 -->|served by| n005
  n005 -.->|related| n007
  n005 -.->|related| n000
  n005 -.->|related| n002
  n013 -->|served by| n006
  n006 -.->|related| n007
  n008 -->|served by| n000
  n008 -.->|related| n010
  n008 -.->|related| n012
  n009 -.->|related| n011
  n010 -->|served by| n002
  n010 -.->|related| n008
  n010 -.->|related| n012
  n011 -.->|related| n009
  n011 -.->|related| n010
  n012 -->|served by| n005
  n012 -.->|related| n008
  n012 -.->|related| n009
  n012 -.->|related| n010
  n013 -->|served by| n000
  n013 -->|served by| n002
  n013 -->|served by| n005
  n013 -.->|related| n008
  n013 -.->|related| n009
  n013 -.->|related| n010
  n013 -.->|related| n011
  n013 -.->|related| n012
```

## Tenancy & access

```mermaid
flowchart LR
  n000("design<br/>audit-log")
  n001("design<br/>automated-secret-rotation")
  n002("design<br/>impersonation")
  n003("design<br/>multi-tenancy")
  n004("design<br/>oauth-mcp-clients")
  n005("design<br/>service-accounts")
  n006("design<br/>tenancy-and-access")
  n007["spec<br/>audit-log"]
  n008["spec<br/>impersonation"]
  n009["spec<br/>multi-tenancy"]
  n010["spec<br/>oauth-mcp"]
  n011["spec<br/>secret-rotation"]
  n012["spec<br/>service-accounts"]
  n013["spec<br/>tenancy-and-access"]
  n007 -->|served by| n000
  n000 -.->|related| n002
  n001 -.->|related| n002
  n001 -.->|related| n000
  n002 -.->|related| n000
  n009 -->|served by| n003
  n003 -.->|related| n006
  n003 -.->|related| n002
  n003 -.->|related| n000
  n004 -.->|related| n002
  n004 -.->|related| n000
  n012 -->|served by| n005
  n005 -.->|related| n006
  n005 -.->|related| n002
  n005 -.->|related| n003
  n005 -.->|related| n000
  n013 -->|served by| n006
  n006 -.->|related| n002
  n006 -.->|related| n000
  n007 -->|served by| n000
  n007 -.->|related| n008
  n007 -.->|related| n012
  n008 -->|served by| n002
  n008 -.->|related| n007
  n008 -.->|related| n009
  n008 -.->|related| n012
  n009 -.->|related| n007
  n009 -.->|related| n008
  n009 -.->|related| n012
  n010 -->|served by| n004
  n010 -.->|related| n008
  n010 -.->|related| n007
  n011 -.->|related| n012
  n011 -.->|related| n007
  n011 -.->|related| n009
  n011 -.->|related| n008
  n012 -.->|related| n007
  n012 -.->|related| n008
  n012 -.->|related| n009
  n013 -->|served by| n002
  n013 -->|served by| n000
  n013 -.->|related| n007
  n013 -.->|related| n008
  n013 -.->|related| n009
  n013 -.->|related| n010
  n013 -.->|related| n011
  n013 -.->|related| n012
```

## Knowledge & admin

```mermaid
flowchart LR
  n000("design<br/>admin-panel")
  n001("design<br/>cold-start-ingestion")
  n002("design<br/>cross-project-patterns")
  n003("design<br/>graph-aware-retrieval")
  n004("design<br/>knowledge-and-admin")
  n005("design<br/>knowledge-freshness")
  n006("design<br/>knowledge-repo-model")
  n007("design<br/>knowledge-stack")
  n008("design<br/>knowledge-write-api")
  n009("design<br/>managed-repo-action-distribution")
  n010("design<br/>mcp-agent-interface-design")
  n011("design<br/>navigation-tree-pattern")
  n012("design<br/>onboarding")
  n013("design<br/>template-schema-migration")
  n014["spec<br/>admin-panel"]
  n015["spec<br/>cold-start-ingestion"]
  n016["spec<br/>fleet-patterns"]
  n017["spec<br/>knowledge-and-admin"]
  n018["spec<br/>knowledge-api"]
  n019["spec<br/>knowledge-freshness"]
  n020["spec<br/>knowledge-schema-migration"]
  n021["spec<br/>managed-workflows"]
  n022["spec<br/>mcp-agent-interface"]
  n023["spec<br/>onboarding"]
  n014 -->|served by| n000
  n000 -.->|related| n008
  n001 -.->|related| n008
  n001 -.->|related| n006
  n002 -.->|related| n008
  n002 -.->|related| n006
  n002 -.->|related| n005
  n002 -.->|related| n003
  n002 -.->|related| n010
  n003 -.->|related| n008
  n003 -.->|related| n006
  n003 -.->|related| n005
  n017 -->|served by| n004
  n004 -.->|related| n007
  n004 -.->|related| n000
  n004 -.->|related| n010
  n019 -->|served by| n005
  n005 -.->|related| n006
  n005 -.->|related| n008
  n006 -.->|related| n008
  n017 -->|served by| n007
  n007 -.->|related| n006
  n007 -.->|related| n008
  n007 -.->|related| n005
  n018 -->|served by| n008
  n008 -.->|related| n006
  n009 -.->|related| n001
  n009 -.->|related| n013
  n009 -.->|related| n008
  n010 -.->|related| n008
  n011 -.->|related| n006
  n011 -.->|related| n008
  n023 -->|served by| n012
  n012 -.->|related| n006
  n012 -.->|related| n008
  n013 -.->|related| n008
  n013 -.->|related| n006
  n013 -.->|related| n009
  n014 -->|served by| n000
  n014 -.->|related| n018
  n015 -.->|related| n018
  n015 -.->|related| n019
  n015 -.->|related| n021
  n015 -.->|related| n023
  n016 -.->|related| n018
  n016 -.->|related| n014
  n016 -.->|related| n019
  n017 -->|served by| n006
  n017 -->|served by| n008
  n017 -->|served by| n005
  n017 -.->|related| n014
  n017 -.->|related| n015
  n017 -.->|related| n016
  n017 -.->|related| n018
  n017 -.->|related| n019
  n017 -.->|related| n020
  n017 -.->|related| n021
  n017 -.->|related| n023
  n018 -->|served by| n006
  n018 -->|served by| n007
  n018 -->|served by| n008
  n018 -.->|related| n014
  n018 -.->|related| n019
  n018 -.->|related| n020
  n019 -->|served by| n005
  n019 -.->|related| n018
  n019 -.->|related| n014
  n020 -.->|related| n018
  n020 -.->|related| n023
  n020 -.->|related| n014
  n020 -.->|related| n019
  n021 -.->|related| n018
  n021 -.->|related| n023
  n021 -.->|related| n014
  n022 -->|served by| n010
  n022 -.->|related| n014
  n022 -.->|related| n018
  n023 -.->|related| n014
  n023 -.->|related| n018
  n023 -.->|related| n020
```

## Delivery & infra

```mermaid
flowchart LR
  n000("design<br/>coder-core-modular-monolith")
  n001("design<br/>continuous-deployment")
  n002("design<br/>delivery-and-infra")
  n003("design<br/>tenant-isolation")
  n004["spec<br/>coder-core-modular-monolith"]
  n005["spec<br/>continuous-deployment"]
  n006["spec<br/>delivery-and-infra"]
  n007["spec<br/>tenant-isolation"]
  n006 -->|served by| n000
  n000 -.->|related| n003
  n005 -->|served by| n001
  n006 -->|served by| n002
  n002 -.->|related| n000
  n002 -.->|related| n001
  n007 -->|served by| n003
  n004 -->|served by| n000
  n004 -.->|related| n005
  n004 -.->|related| n007
  n006 -->|served by| n000
  n006 -.->|related| n005
  n006 -.->|related| n007
```

## Other

### System Overview

```mermaid
flowchart LR
  n000("design<br/>system-overview")
```

## ADR fan-out

Which active artifacts cite each ADR via `decided_by`. Use this
to spot ADRs whose decisions ripple into multiple components.

| ADR | Cited by |
|---|---|
| [0001](./adrs/0001-*.md) | [design/knowledge-repo-model](./designs/active/knowledge-repo-model.md), [design/system-overview](./designs/active/system-overview.md) |
| [0002](./adrs/0002-*.md) | [design/knowledge-repo-model](./designs/active/knowledge-repo-model.md) |
| [0003](./adrs/0003-*.md) | [design/knowledge-repo-model](./designs/active/knowledge-repo-model.md) |
| [0004](./adrs/0004-*.md) | [design/knowledge-repo-model](./designs/active/knowledge-repo-model.md) |
| [0005](./adrs/0005-*.md) | [design/multi-tenancy](./designs/active/multi-tenancy.md), [design/system-overview](./designs/active/system-overview.md) |
| [0006](./adrs/0006-*.md) | [design/impersonation](./designs/active/impersonation.md), [design/service-accounts](./designs/active/service-accounts.md), [design/system-overview](./designs/active/system-overview.md), [design/worker-roles](./designs/active/worker-roles.md) |
| [0007](./adrs/0007-*.md) | [design/system-overview](./designs/active/system-overview.md), [design/worker-roles](./designs/active/worker-roles.md) |
| [0008](./adrs/0008-*.md) | [design/knowledge-repo-model](./designs/active/knowledge-repo-model.md), [design/system-overview](./designs/active/system-overview.md) |
| [0014](./adrs/0014-*.md) | [design/knowledge-freshness](./designs/active/knowledge-freshness.md) |
| [0016](./adrs/0016-*.md) | [design/orchestrator-github-state-reconciliation](./designs/active/orchestrator-github-state-reconciliation.md) |
| [0017](./adrs/0017-*.md) | [design/post-pr-ci-fix-loop](./designs/active/post-pr-ci-fix-loop.md) |
| [0018](./adrs/0018-*.md) | [design/managed-repo-action-distribution](./designs/active/managed-repo-action-distribution.md) |
| [0019](./adrs/0019-*.md) | [design/template-schema-migration](./designs/active/template-schema-migration.md) |
| [0020](./adrs/0020-*.md) | [design/template-schema-migration](./designs/active/template-schema-migration.md) |
| [0021](./adrs/0021-*.md) | [design/template-schema-migration](./designs/active/template-schema-migration.md) |
| [0022](./adrs/0022-*.md) | [design/cross-project-patterns](./designs/active/cross-project-patterns.md) |
| [0023](./adrs/0023-*.md) | [design/cross-project-patterns](./designs/active/cross-project-patterns.md) |
| [0024](./adrs/0024-*.md) | [design/cross-project-patterns](./designs/active/cross-project-patterns.md) |
| [0027](./adrs/0027-*.md) | [design/role-prompt-knowledge-layout](./designs/active/role-prompt-knowledge-layout.md) |
| [0029](./adrs/0029-*.md) | [design/navigation-tree-pattern](./designs/active/navigation-tree-pattern.md) |
