---
id: knowledge-api
title: Knowledge API
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-15
last_verified_at: 2026-04-15
served_by_designs: [knowledge-write-api, knowledge-repo-model]
related_specs: [knowledge-freshness]
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

## Interfaces

- `GET /v1/projects/{id}/knowledge/{type}` — list registry entries.
- `GET /v1/projects/{id}/knowledge/{type}/{artifact_id}` — fetch one.
- `GET /v1/projects/{id}/knowledge/glossary` — glossary terms.
- `POST /v1/projects/{id}/knowledge/{type}` — create.
- `PUT /v1/projects/{id}/knowledge/{type}/{artifact_id}` — update.
- `GET /v1/projects/{id}/knowledge/_metrics` — cache metrics.
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

## Links

- Designs: (none yet)
- Related components: multi-tenancy, admin-panel
