# Coder system — cross-link graph

> Generated from `served_by_designs`, `implements_specs`, `decided_by`, and `related_*` frontmatter on each active artifact. Hand edits are lost on the next `scripts/render_graph.py` run. The taxonomy tree lives in [`INDEX.md`](./INDEX.md); this file shows the **non-tree** relationships.

Mermaid notation: `[spec]` rectangle, `(design)` rounded. Solid `-->` is `served_by_designs` / `implements_specs` (the spec/design pair that realises a contract). Dashed `-.->` is `related_*` (sibling cross-link).

## Pipeline operations

```mermaid
flowchart LR
  n000("design<br/>pipeline-operations")
  n001["spec<br/>branch-cleanup"]
  n002["spec<br/>escalations"]
  n003["spec<br/>observability"]
  n004["spec<br/>pipeline-operations"]
  n005["spec<br/>self-healing"]
  n006["spec<br/>task-orchestration"]
  n004 -->|served by| n000
  n001 -.->|related| n006
  n001 -.->|related| n003
  n002 -.->|related| n006
  n002 -.->|related| n003
  n005 -.->|related| n006
  n005 -.->|related| n003
  n005 -.->|related| n002
```

## Worker roles

```mermaid
flowchart LR
  n000("design<br/>worker-roles")
  n001["spec<br/>architect-worker"]
  n002["spec<br/>developer-worker"]
  n003["spec<br/>pm-worker"]
  n004["spec<br/>reviewer-worker"]
  n005["spec<br/>team-manager-worker"]
  n006["spec<br/>worker-roles"]
  n002 -->|served by| n000
  n004 -->|served by| n000
  n006 -->|served by| n000
```

## Tenancy & access

```mermaid
flowchart LR
  n000("design<br/>tenancy-and-access")
  n001["spec<br/>audit-log"]
  n002["spec<br/>impersonation"]
  n003["spec<br/>mcp-agent-interface"]
  n004["spec<br/>multi-tenancy"]
  n005["spec<br/>oauth-mcp"]
  n006["spec<br/>secret-rotation"]
  n007["spec<br/>service-accounts"]
  n008["spec<br/>tenancy-and-access"]
  n008 -->|served by| n000
  n001 -.->|related| n002
  n001 -.->|related| n007
  n002 -.->|related| n001
  n003 -.->|related| n002
  n003 -.->|related| n007
  n003 -.->|related| n001
  n003 -.->|related| n004
  n005 -.->|related| n002
  n005 -.->|related| n001
  n006 -.->|related| n007
  n006 -.->|related| n001
  n006 -.->|related| n004
  n006 -.->|related| n002
```

## Knowledge & admin

```mermaid
flowchart LR
  n000("design<br/>knowledge-and-admin")
  n001["spec<br/>admin-panel"]
  n002["spec<br/>cold-start-ingestion"]
  n003["spec<br/>fleet-patterns"]
  n004["spec<br/>knowledge-and-admin"]
  n005["spec<br/>knowledge-api"]
  n006["spec<br/>knowledge-freshness"]
  n007["spec<br/>knowledge-schema-migration"]
  n008["spec<br/>managed-workflows"]
  n009["spec<br/>onboarding"]
  n004 -->|served by| n000
  n002 -.->|related| n009
  n002 -.->|related| n005
  n002 -.->|related| n006
  n003 -.->|related| n005
  n003 -.->|related| n001
  n003 -.->|related| n006
  n005 -.->|related| n006
  n005 -.->|related| n007
  n006 -.->|related| n005
  n006 -.->|related| n001
  n007 -.->|related| n005
  n007 -.->|related| n009
  n007 -.->|related| n001
  n007 -.->|related| n006
  n008 -.->|related| n005
  n008 -.->|related| n009
  n008 -.->|related| n001
  n009 -.->|related| n007
```

## Delivery & infra

```mermaid
flowchart LR
  n000("design<br/>delivery-and-infra")
  n001["spec<br/>continuous-deployment"]
  n002["spec<br/>delivery-and-infra"]
  n003["spec<br/>tenant-isolation"]
  n002 -->|served by| n000
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
| [0001](./adrs/0001-*.md) | [design/system-overview](./designs/active/system-overview.md) |
| [0005](./adrs/0005-*.md) | [design/system-overview](./designs/active/system-overview.md) |
| [0006](./adrs/0006-*.md) | [design/system-overview](./designs/active/system-overview.md), [design/worker-roles](./designs/active/worker-roles.md) |
| [0007](./adrs/0007-*.md) | [design/system-overview](./designs/active/system-overview.md), [design/worker-roles](./designs/active/worker-roles.md) |
| [0008](./adrs/0008-*.md) | [design/system-overview](./designs/active/system-overview.md) |
