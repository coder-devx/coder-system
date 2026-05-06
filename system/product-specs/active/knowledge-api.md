---
id: knowledge-api
title: Knowledge API
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: [knowledge-write-api, knowledge-repo-model]
related_specs: [knowledge-freshness]
parent: knowledge-and-admin
---

# Knowledge API

## What it is

The single authoritative surface in `coder-core` for reading and writing
a project's knowledge repo (specs, designs, ADRs, services, repos,
roles, integrations, runbooks, glossary). Every worker and the admin
panel go through it — no caller talks to GitHub directly. Reads return
parsed, typed artifacts with resolvable cross-links. Writes commit to
the Git-backed repo with frontmatter validation, cross-link integrity
checks, and actor attribution.

## Capabilities

- List and fetch knowledge artifacts by `{type}` and `{type}/{id}` with
  parsed frontmatter and markdown body — never raw YAML.
- Typed Pydantic models per artifact type matching each `_TEMPLATE.md`
  schema one-to-one; schema-invalid frontmatter yields a structured
  error naming the offending field, not a 500.
- Cross-link resolution: traverse spec → design → ADR etc. without
  re-fetching from GitHub. Broken links are surfaced in the response,
  not silently dropped.
- Project-scoped: an artifact in one project returns `404` from
  another.
- Create and update artifacts (specs, designs, ADRs) via write endpoints
  that commit directly to `main` with structured commit messages
  attributing the worker actor.
- Cross-link validation on write: rejects writes referencing
  non-existent IDs. Self-references allowed. Creates atomically add the
  new artifact to the registry in the same commit.
- Status changes trigger file moves (create at new path + delete old +
  registry update) in one commit.
- In-memory TTL cache keyed on `(project, ref, path)` with
  `knowledge_cache_hit_total` metric.
- **Ship endpoint.** `POST /v1/projects/{id}/knowledge/ship` atomically
  lands a WIP-to-active merge in a single GitHub Git Trees commit:
  `active/` edits or creates, the WIP file delete, and both
  `{folder}/registry.yaml` rewrites. The body carries
  `{wip_id, wip_type, merges[], attestation, commit_message}` — the
  reviewer attestation pairs every WIP acceptance criterion with either
  a target `active/` artifact + section or an explicit drop reason.
  Validation (AC coverage, cross-link resolution against the post-merge
  snapshot, frontmatter shape, `type`/`id` immutability) runs in-memory
  against the HEAD snapshot; any failure returns 4xx with nothing
  written. Concurrency serialises on the branch ref SHA; the loser of
  a race gets 409. Template paths are refused with a pointer to the
  template-migration path. Behind `settings.ship_gate_enabled`.
- **Orphan-WIP query.** `GET /v1/projects/{id}/knowledge/wips?shipped=true`
  returns the WIPs whose correlated developer task is `closed` + PR
  `merged` but whose file still sits in `wip/`. Used by Team Manager's
  close-cycle backstop and the admin ship-gate "needs attention" list.
- **Graph retrieval.** `GET /v1/projects/{id}/knowledge/graph` returns
  the artifact subgraph reachable from a start node in a single
  round-trip, replacing the N+1 serial-fetch pattern in worker context
  assembly. Parameters: `start=<type/id>` (required), `depth` (default
  2, max 3), `edge_types` (comma-list restricting which cross-link
  fields to follow; workers always pass an explicit value via named
  presets in `coder_core/knowledge/graph_client.py`), `min_freshness`
  (below-floor nodes returned as stubs with no body and no outgoing
  traversal), `max_nodes` (default 200, hard cap 500). Traversal is BFS
  ordered `(type, id)` lex; bounded by `max_nodes`, `depth`, and a
  per-node fan-out cap of 50 edges. Truncated responses set
  `truncated: true` and populate `truncated_at[]` with
  `{parent_id, edge_type, target_id, reason}` per dropped edge
  (`reason ∈ {"max_nodes", "fan_out_cap"}`). Cache coherence: the
  handler pins a commit SHA at request start and uses it for every node
  in the response — no node in one response can disagree with another.
  Every node carries the same Pydantic-typed envelope as the
  single-artifact `GET` (frontmatter, body, freshness, edges[]).
  Metrics: `knowledge_graph_fetch_seconds_bucket{project,depth_bucket}`
  histogram and `knowledge_graph_nodes_returned{project}` gauge on the
  `_metrics` endpoint; p95 target ≤ 2 s at depth=2. Behind
  `CODER_KNOWLEDGE_GRAPH_ENABLED` (default off on first deploy) with a
  per-project escape hatch column `projects.knowledge_graph_enabled`
  (NULL = inherit fleet default). When off, the endpoint returns 503
  and worker conversions fall back to the prior serial walk.

## Interfaces

- `GET /v1/projects/{id}/knowledge/{type}` — list registry entries.
- `GET /v1/projects/{id}/knowledge/{type}/{artifact_id}` — fetch one.
- `GET /v1/projects/{id}/knowledge/glossary` — glossary terms.
- `POST /v1/projects/{id}/knowledge/{type}` — create.
- `PUT /v1/projects/{id}/knowledge/{type}/{artifact_id}` — update.
- `POST /v1/projects/{id}/knowledge/ship` — atomic WIP→active merge.
- `GET /v1/projects/{id}/knowledge/wips?shipped=true` — orphan WIP list.
- `GET /v1/projects/{id}/knowledge/graph` — artifact subgraph fetch.
- `GET /v1/projects/{id}/knowledge/_metrics` — cache + graph metrics.
- `GET /v1/projects/{id}/knowledge/_files/{path}` — bytes passthrough
  escape hatch.

## Dependencies

- multi-tenancy — project scoping and auth.
- GitHub Contents API — source of truth; accessed via a `GitHubClient`
  with `create_file` / `delete_file` helpers.
- Registry (`registry.yaml`) — served directly for list views, never
  the generated `REGISTRY.md`.

## Evolution

- 0002 Knowledge repo read API (shipped 2026-04) — typed read routes,
  cross-link resolution with broken-link surfacing, TTL cache with
  metrics endpoint.
- 0014 Knowledge write API (shipped 2026-04) — `POST`/`PUT` wrapping
  GitHub Contents API, frontmatter validation, cross-link integrity,
  actor-attributed commits, status-change file moves.
- 0044 Write-through enforcement on ship (shipped 2026-04-18) —
  `POST /v1/projects/{id}/knowledge/ship` atomic WIP→active merge via
  Git Trees (single commit covering every touched file + both
  registries + WIP delete) behind `settings.ship_gate_enabled`; new
  `GET /v1/projects/{id}/knowledge/wips?shipped=true` orphan query
  powering the close-cycle backstop and the admin ship-gate panel;
  pre-commit validator enforces AC coverage, cross-link resolution
  against the post-merge snapshot, and template-path refusal.
- 0035 Inline knowledge editor (shipped 2026-04-19, body-only) —
  admin-panel now drives the existing `PUT /knowledge/{type}/{id}`
  endpoint from the artifact view (body-only payload, shallow
  frontmatter merge still server-supported for phase 2). No backend
  changes. New `knowledge_edited` structured log event at save
  (`{project_id, artifact_type, artifact_id, commit_sha}`) flows
  through the existing `coder_core.api.knowledge` logger. SHA
  conflicts bubble as 502 `github_upstream` for the editor's
  "reload" branch; 422 `invalid_frontmatter` / broken cross-links
  render inline.
- 0046 Graph-aware knowledge retrieval (shipped 2026-05-06) — new
  `GET /v1/projects/{id}/knowledge/graph` endpoint returns the BFS
  artifact subgraph in one round-trip, replacing the N+1 serial-fetch
  pattern in all authoring workers. Bounded by `max_nodes` (default
  200, hard cap 500), `depth` (max 3), and per-node fan-out cap (50);
  truncated responses surface `truncated_at[]`. Below-floor nodes
  returned as stubs when `min_freshness` is set. SHA-pinned
  cache-coherence invariant. Per-worker call presets in
  `coder_core/knowledge/graph_client.py`. New graph metrics on
  `_metrics`. Behind `CODER_KNOWLEDGE_GRAPH_ENABLED` (default off)
  with per-project `projects.knowledge_graph_enabled` escape hatch.

## Links

- Designs: [knowledge-write-api](../../designs/active/knowledge-write-api.md),
  [knowledge-repo-model](../../designs/active/knowledge-repo-model.md),
  [knowledge-stack](../../designs/active/knowledge-stack.md)
- Related components: [multi-tenancy](./multi-tenancy.md),
  [admin-panel](./admin-panel.md),
  [knowledge-freshness](./knowledge-freshness.md),
  [audit-log](./audit-log.md),
  [task-orchestration](./task-orchestration.md)
