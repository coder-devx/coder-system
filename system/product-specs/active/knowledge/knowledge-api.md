---
id: knowledge-api
title: Knowledge API
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: Read-through layer over the knowledge repo with per-project cache.
served_by_designs: [knowledge-repo-model, knowledge-stack, knowledge-write-api]
related_specs: [admin-panel, audit-log, knowledge-freshness, knowledge-schema-migration, multi-tenancy, task-orchestration]
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
- **Schema-drift guard.** Optional `?min_schema_version=N` param on
  single-artifact fetch endpoints. Returns `409 SCHEMA_DRIFT` when the
  project's recorded `template_version < N`. The 409 body carries the
  artifact (callers may opt in to using it anyway) plus
  `pending_migrations: [{number, slug, description}]` identifying what
  hasn't applied yet. Absent param preserves legacy 200 behaviour.
  Mirrors the `min_freshness` pattern from
  [knowledge-freshness](./knowledge-freshness.md).
- **Template version endpoints.** `GET /v1/projects/{id}/template/version`
  returns `{template_version, current_version, pending: [{number, slug,
  description}]}` under per-project auth. Used by workers' fall-back
  schema checks and the admin template-migrations page.
  `GET /v1/_admin/template/migrations` (admin JWT) returns the fleet
  migration matrix: `[{project_id, template_version, pending_count,
  oldest_pending_pr_age, last_attempted_at, last_error}]`.

## Interfaces

- `GET /v1/projects/{id}/knowledge/{type}` — list registry entries.
- `GET /v1/projects/{id}/knowledge/{type}/{artifact_id}` — fetch one;
  optional `?min_schema_version=N` yields `409 SCHEMA_DRIFT`.
- `GET /v1/projects/{id}/knowledge/glossary` — glossary terms.
- `POST /v1/projects/{id}/knowledge/{type}` — create.
- `PUT /v1/projects/{id}/knowledge/{type}/{artifact_id}` — update.
- `POST /v1/projects/{id}/knowledge/ship` — atomic WIP→active merge.
- `GET /v1/projects/{id}/knowledge/wips?shipped=true` — orphan WIP
  list.
- `GET /v1/projects/{id}/knowledge/_metrics` — cache metrics.
- `GET /v1/projects/{id}/knowledge/_files/{path}` — bytes passthrough
  escape hatch.
- `GET /v1/projects/{id}/template/version` — per-project schema-version
  status (per-project auth).
- `GET /v1/_admin/template/migrations` — fleet migration matrix (admin
  JWT).

## Dependencies

- multi-tenancy — project scoping and auth.
- GitHub Contents API — source of truth; accessed via a `GitHubClient`
  with `create_file` / `delete_file` helpers.
- Registry (`registry.yaml`) — served directly for list views, never
  the generated `REGISTRY.md`.

## Evolution

- 2026-04 — Typed read + write API: read routes with cross-link
  resolution, write endpoints wrapping GitHub Contents, frontmatter
  validation, actor-attributed commits, status-change file moves
  (specs 0002, 0014).
- 2026-04-18/19 — Ship gate + inline editor: atomic WIP→active
  `/knowledge/ship` via Git Trees with pre-commit validator;
  body-only inline editor wired from admin-panel through the
  existing PUT endpoint (specs 0044, 0035).
- 2026-05-06 — Template schema-migration signal: `?min_schema_version=N`
  → `409 SCHEMA_DRIFT`; version + matrix endpoints (spec 0047, see
  [knowledge-schema-migration](./knowledge-schema-migration.md)).

## Links

- Designs: [knowledge-write-api](../../../designs/active/knowledge/knowledge-write-api.md),
  [knowledge-repo-model](../../../designs/active/knowledge/knowledge-repo-model.md),
  [knowledge-stack](../../../designs/active/knowledge/knowledge-stack.md)
- Related components: [multi-tenancy](../tenancy/multi-tenancy.md),
  [admin-panel](./admin-panel.md),
  [knowledge-freshness](./knowledge-freshness.md),
  [knowledge-schema-migration](./knowledge-schema-migration.md),
  [audit-log](../tenancy/audit-log.md),
  [task-orchestration](../pipeline/task-orchestration.md)
