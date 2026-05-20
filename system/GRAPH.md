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
  n015 -.->|related| n013
  n015 -.->|related| n011
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
  n001("design<br/>coder-product-template")
  n002("design<br/>coder-studio-founder")
  n003("design<br/>cold-start-ingestion")
  n004("design<br/>cross-project-patterns")
  n005("design<br/>graph-aware-retrieval")
  n006("design<br/>knowledge-and-admin")
  n007("design<br/>knowledge-freshness")
  n008("design<br/>knowledge-repo-model")
  n009("design<br/>knowledge-stack")
  n010("design<br/>knowledge-write-api")
  n011("design<br/>managed-repo-action-distribution")
  n012("design<br/>mcp-agent-interface-design")
  n013("design<br/>navigation-tree-pattern")
  n014("design<br/>onboarding")
  n015("design<br/>studio")
  n016("design<br/>studio-b2c-portfolio")
  n017("design<br/>studio-product-integrations")
  n018("design<br/>template-schema-migration")
  n019["spec<br/>admin-panel"]
  n020["spec<br/>coder-product-template"]
  n021["spec<br/>coder-studio-founder"]
  n022["spec<br/>cold-start-ingestion"]
  n023["spec<br/>fleet-patterns"]
  n024["spec<br/>knowledge-and-admin"]
  n025["spec<br/>knowledge-api"]
  n026["spec<br/>knowledge-freshness"]
  n027["spec<br/>knowledge-schema-migration"]
  n028["spec<br/>managed-workflows"]
  n029["spec<br/>mcp-agent-interface"]
  n030["spec<br/>onboarding"]
  n031["spec<br/>studio"]
  n032["spec<br/>studio-b2c-portfolio"]
  n033["spec<br/>studio-product-integrations"]
  n019 -->|served by| n000
  n000 -.->|related| n010
  n020 -->|served by| n001
  n001 -.->|related| n015
  n001 -.->|related| n016
  n001 -.->|related| n017
  n001 -.->|related| n000
  n021 -->|served by| n002
  n002 -.->|related| n015
  n002 -.->|related| n016
  n002 -.->|related| n000
  n003 -.->|related| n010
  n003 -.->|related| n008
  n004 -.->|related| n010
  n004 -.->|related| n008
  n004 -.->|related| n007
  n004 -.->|related| n005
  n004 -.->|related| n012
  n005 -.->|related| n010
  n005 -.->|related| n008
  n005 -.->|related| n007
  n024 -->|served by| n006
  n006 -.->|related| n009
  n006 -.->|related| n000
  n006 -.->|related| n012
  n026 -->|served by| n007
  n007 -.->|related| n008
  n007 -.->|related| n010
  n008 -.->|related| n010
  n024 -->|served by| n009
  n009 -.->|related| n008
  n009 -.->|related| n010
  n009 -.->|related| n007
  n025 -->|served by| n010
  n010 -.->|related| n008
  n011 -.->|related| n003
  n011 -.->|related| n018
  n011 -.->|related| n010
  n012 -.->|related| n010
  n013 -.->|related| n008
  n013 -.->|related| n010
  n030 -->|served by| n014
  n014 -.->|related| n008
  n014 -.->|related| n010
  n031 -->|served by| n015
  n015 -.->|related| n016
  n015 -.->|related| n002
  n015 -.->|related| n001
  n015 -.->|related| n017
  n015 -.->|related| n000
  n032 -->|served by| n016
  n016 -.->|related| n015
  n016 -.->|related| n002
  n016 -.->|related| n001
  n016 -.->|related| n017
  n016 -.->|related| n000
  n033 -->|served by| n017
  n017 -.->|related| n015
  n017 -.->|related| n016
  n017 -.->|related| n000
  n018 -.->|related| n010
  n018 -.->|related| n008
  n018 -.->|related| n011
  n019 -.->|related| n032
  n020 -.->|related| n032
  n020 -.->|related| n033
  n020 -.->|related| n019
  n021 -.->|related| n019
  n022 -.->|related| n025
  n022 -.->|related| n026
  n022 -.->|related| n028
  n022 -.->|related| n030
  n023 -.->|related| n025
  n023 -.->|related| n019
  n023 -.->|related| n026
  n024 -->|served by| n008
  n024 -->|served by| n010
  n024 -->|served by| n007
  n024 -.->|related| n019
  n024 -.->|related| n022
  n024 -.->|related| n023
  n024 -.->|related| n025
  n024 -.->|related| n026
  n024 -.->|related| n027
  n024 -.->|related| n028
  n024 -.->|related| n030
  n025 -->|served by| n008
  n025 -->|served by| n009
  n025 -->|served by| n010
  n025 -.->|related| n019
  n025 -.->|related| n026
  n025 -.->|related| n027
  n026 -->|served by| n007
  n026 -.->|related| n025
  n026 -.->|related| n019
  n027 -.->|related| n025
  n027 -.->|related| n030
  n027 -.->|related| n019
  n027 -.->|related| n026
  n028 -.->|related| n025
  n028 -.->|related| n030
  n028 -.->|related| n019
  n029 -->|served by| n012
  n029 -.->|related| n019
  n029 -.->|related| n025
  n030 -.->|related| n019
  n030 -.->|related| n025
  n030 -.->|related| n027
  n031 -.->|related| n019
  n032 -.->|related| n019
  n033 -.->|related| n019
```

## Delivery & infra

```mermaid
flowchart LR
  n000("design<br/>branch-protection")
  n001("design<br/>coder-core-modular-monolith")
  n002("design<br/>continuous-deployment")
  n003("design<br/>delivery-and-infra")
  n004("design<br/>tenant-isolation")
  n005("design<br/>test-harness-reliability")
  n006["spec<br/>branch-protection"]
  n007["spec<br/>coder-core-modular-monolith"]
  n008["spec<br/>continuous-deployment"]
  n009["spec<br/>delivery-and-infra"]
  n010["spec<br/>tenant-isolation"]
  n011["spec<br/>test-harness-reliability"]
  n006 -->|served by| n000
  n000 -.->|related| n002
  n009 -->|served by| n001
  n001 -.->|related| n004
  n008 -->|served by| n002
  n009 -->|served by| n003
  n003 -.->|related| n001
  n003 -.->|related| n002
  n010 -->|served by| n004
  n011 -->|served by| n005
  n005 -.->|related| n002
  n005 -.->|related| n004
  n006 -.->|related| n008
  n007 -->|served by| n001
  n007 -.->|related| n008
  n007 -.->|related| n010
  n009 -->|served by| n001
  n011 -.->|related| n008
  n011 -.->|related| n010
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
| [0009](./adrs/0009-*.md) | [design/studio-b2c-portfolio](./designs/active/studio-b2c-portfolio.md), [design/studio-product-integrations](./designs/active/studio-product-integrations.md) |
| [0011](./adrs/0011-*.md) | [design/test-harness-reliability](./designs/active/test-harness-reliability.md) |
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
| [0032](./adrs/0032-*.md) | [design/coder-product-template](./designs/active/coder-product-template.md), [design/studio-b2c-portfolio](./designs/active/studio-b2c-portfolio.md), [design/system-overview](./designs/active/system-overview.md) |
| [0033](./adrs/0033-*.md) | [design/studio-b2c-portfolio](./designs/active/studio-b2c-portfolio.md), [design/system-overview](./designs/active/system-overview.md) |
| [0034](./adrs/0034-*.md) | [design/studio-b2c-portfolio](./designs/active/studio-b2c-portfolio.md) |
| [0035](./adrs/0035-*.md) | [design/coder-studio-founder](./designs/active/coder-studio-founder.md), [design/studio-b2c-portfolio](./designs/active/studio-b2c-portfolio.md) |
| [0036](./adrs/0036-*.md) | [design/coder-product-template](./designs/active/coder-product-template.md) |
| [0038](./adrs/0038-*.md) | [design/developer-worker](./designs/active/developer-worker.md) |
| [0039](./adrs/0039-*.md) | [design/reviewer-worker](./designs/active/reviewer-worker.md) |
| [0041](./adrs/0041-*.md) | [design/admin-panel](./designs/active/admin-panel.md) |
