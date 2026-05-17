# Active designs — entry point

The architect's knowledge base. Each leaf is a current-state design of
one component; each category rollup groups related leaves and lists the
cross-cutting concerns that span them.

## Categories

- **[System overview](./active/system-overview.md)** — what runs, where; the big picture across all categories.
- **[Pipeline operations](./active/pipeline-operations.md)** — task flow, dispatch, lifecycle, recovery, observability.
- **[Workers](./active/worker-roles.md)** — role contracts, per-role workers, auth and env wiring, prompt layout.
- **[Tenancy & access](./active/tenancy-and-access.md)** — multi-tenancy, audit, impersonation, secrets, OAuth/MCP clients.
- **[Knowledge & admin](./active/knowledge-and-admin.md)** — knowledge API, freshness, MCP agent interface, admin panel surfaces.
- **[Delivery & infra](./active/delivery-and-infra.md)** — CI/CD, module boundaries, tenant-isolation harness.

## How to read

1. Start here → pick a category → open its rollup (above).
2. Each rollup has `## Components` listing leaves with one-liners.
3. Open the leaf for current state; each leaf ends with
   `## Where in code` pointing at symbols in `coder-core` / `coder-admin`.
4. For decision rationale (why X over Y), see [`adrs/REGISTRY.md`](../adrs/REGISTRY.md).

## Role-tuned routing

Each role has a per-task reading map keyed by spec topic:

- [Architect](../roles/software-architect/INDEX.md)
- [Product Manager](../roles/product-manager/INDEX.md)
- [Reviewer](../roles/reviewer/INDEX.md)
- [Team Manager](../roles/team-manager/INDEX.md)

The role INDEX routes through these category rollups; treat this file
as the table of contents and the role INDEX as your task-specific lens.

## Conventions for designs in here

- Subject-slug filenames (no numeric prefixes) — see [AGENTS.md](../../AGENTS.md).
- **One component per design, current state only.** Rollout / history /
  decisions go in `## Evolution` (terse) or in ADRs — never in the body.
  Length follows content; smell test at ~200 body lines (look hard for
  fused topics, padding, or rollout narrative that belongs elsewhere).
  See [architect role doc](../roles/software-architect/role.md)
  §"What a good design looks like" for the full discipline.
- Every leaf ends with `## Where in code` (symbol anchors, never line numbers;
  enforced by `scripts/validate.py`).
- Cross-links use ids in frontmatter, paths in body markdown.
