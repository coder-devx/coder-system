---
id: knowledge-and-admin
title: Knowledge & admin
type: index
status: active
owner: ro
created: '2026-05-17'
updated: '2026-05-17'
last_verified_at: '2026-05-17'
summary: Knowledge API, freshness, MCP agent interface, and admin panel surfaces.
implements_specs: [knowledge-and-admin]
related_designs: [system-overview, knowledge-stack, admin-panel, mcp-agent-interface-design]
affects_services: [coder-core, coder-admin]
parent: ~
---

# Knowledge & admin

Engineering shape of how project knowledge is served, kept fresh, and
surfaced to operators (admin panel + MCP agent interface).

## What this category covers

Engineering counterpart of the
[knowledge-and-admin](../../product-specs/active/knowledge-and-admin.md)
spec. Groups the designs that govern:

- The per-project knowledge repo's content lifecycle (read, write, ship, freshness).
- External agent access (MCP) and operator UI (admin panel).
- Bulk ingestion (cold-start) and cross-project pattern surfacing.

## Components

**Knowledge stack** — the IO and shape of the knowledge repo itself:

- [knowledge-stack](./knowledge/knowledge-stack.md) — sub-rollup; reads, writes, freshness
  - [knowledge-repo-model](./knowledge/knowledge-repo-model.md) — per-project repo shape; artifact types; validator contract
    - [navigation-tree-pattern](./knowledge/navigation-tree-pattern.md) — the parent/INDEX tree pattern this organisation follows
  - [knowledge-write-api](./knowledge/knowledge-write-api.md) — create / update / `/ship` endpoints; AC attestation
  - [knowledge-freshness](./knowledge/knowledge-freshness.md) — `last_verified_at` semantics; nightly Architect audit

**Retrieval & ingestion:**

- [graph-aware-retrieval](./knowledge/graph-aware-retrieval.md) — subgraph fetch in one call; reverse-edge traversal (design 0046).
- [cold-start-ingestion](./knowledge/cold-start-ingestion.md) — bootstrap a project's knowledge repo from existing source (spec 0045).
- [cross-project-patterns](./knowledge/cross-project-patterns.md) — surface recurring failure / success patterns across projects.
- [template-schema-migration](./knowledge/template-schema-migration.md) — propagate template/ schema changes into every managed project's knowledge repo.
- [managed-repo-action-distribution](./knowledge/managed-repo-action-distribution.md) — distribute shared GitHub Actions to every managed project repo.

**External surfaces:**

- [mcp-agent-interface-design](./knowledge/mcp-agent-interface-design.md) — MCP server exposing knowledge + task tools to external agents (spec 0049).
- [admin-panel](./knowledge/admin-panel.md) — operator UI: project switcher, knowledge browser, pipeline UI, audit log, drive mode.
- [onboarding](./knowledge/onboarding.md) — new-project bootstrap: knowledge repo, GCP project, GitHub org, role SAs.

## Cross-cutting concerns

- **Auth on knowledge writes**: every mutation routes through
  `coder_core.access.load_in_project` and emits a
  `record_audit_event` row inside the same transaction (see
  [audit-log](./tenancy/audit-log.md)).
- **Cross-link integrity**: `scripts/validate.py` rejects any
  cross-link to a missing artifact id; renderers (`render_registry.py`,
  `render_index.py`, `render_graph.py`) keep the human-readable
  views in sync with `registry.yaml`.
- **MCP tool surface**: the admin panel and external agents share
  the same Knowledge MCP tools (`get_knowledge`, `list_knowledge`,
  `submit_knowledge`) — adapter-neutral business logic per the
  modular-monolith contract.

## Links

- Specs: [knowledge-and-admin](../../product-specs/active/knowledge-and-admin.md), [knowledge-api](../../product-specs/active/knowledge/knowledge-api.md), [knowledge-freshness](../../product-specs/active/knowledge/knowledge-freshness.md), [admin-panel](../../product-specs/active/knowledge/admin-panel.md), [onboarding](../../product-specs/active/knowledge/onboarding.md)
- ADRs: [0026](../../adrs/0026-share-numeric-id-pool-between-specs-and-designs.md) (shared id pool), [0029](../../adrs/0029-unified-knowledge-index.md) (unified INDEX), [0030](../../adrs/0030-best-effort-preload.md) (preload pattern)
