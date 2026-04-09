---
id: "0002"
title: Knowledge repo read API
type: spec
status: wip
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0001", "0003"]
---

# Knowledge repo read API

**Phase:** Now (foundation)
**Progress:** 1 / 7 acceptance criteria

## Problem

Every project has its own `coder-system`-shaped knowledge repo on
GitHub, and every worker and the admin panel need to read it
consistently — frontmatter, registries, cross-links, and all. Today,
each caller would have to hit GitHub directly, re-implement YAML
parsing, and re-implement link resolution. That duplication will rot
fast and means workers and admin can diverge in their view of "truth".
We need one authoritative read API in `coder-core` that every consumer
goes through.

## Users / personas

- **Role workers** (Architect, PM, Developer, Reviewer, SysAdmin) —
  fetch specs, designs, ADRs, and runbooks relevant to a task.
- **Admin Panel** — render a browsable view of any project's knowledge.
- **Local agent** impersonating a role — loads the same knowledge slice
  the equivalent worker would see.
- **Developer** building `coder-core` — needs one place to add caching,
  auth, and project-scoping rather than sprinkling it across callers.

## Goals

- A single `GET` surface that returns parsed knowledge artifacts for a
  given project, addressable by `{type}/{id}` and `{type}/{folder}/{id}`.
- Frontmatter is parsed and typed on the way out — callers never see raw
  YAML.
- Cross-links are resolvable: an API consumer can traverse from a spec
  to its served designs, and from a design to its decided_by ADRs,
  without re-fetching from GitHub.
- Registry view is served directly from `registry.yaml`, never from the
  generated `REGISTRY.md`.
- Responses are consistently project-scoped — no global or cross-project
  reads.

## Non-goals

- Write API for knowledge (agents proposing changes via PR comes later).
- Full-text search across a knowledge repo (v0 is navigation + fetch).
- Webhook-driven cache invalidation — v0 can be pull-on-read with a
  short TTL.
- Rendering Mermaid or other diagrams server-side.

## Scope

- `GET /projects/{id}/knowledge/{type}` — list registry entries for a type
  (specs, designs, adrs, services, repos, roles, integrations, runbooks).
- `GET /projects/{id}/knowledge/{type}/{artifact_id}` — fetch one artifact
  with parsed frontmatter + markdown body.
- `GET /projects/{id}/knowledge/glossary` — return glossary terms.
- GitHub client with a short in-memory TTL cache keyed on `(project, ref, path)`.
- Pydantic models that match each `_TEMPLATE.md` schema one-to-one.
- Link resolution helper that turns cross-link IDs into usable references
  the caller can follow.

## Acceptance criteria

- [ ] `GET /projects/{id}/knowledge/specs` returns every entry in that
      project's `product-specs/registry.yaml` with parsed fields.
- [ ] Fetching an artifact returns a typed object with `frontmatter` and
      `body_markdown`, never raw YAML.
- [ ] A cross-link from spec → design resolves to a valid reference the
      caller can pass straight back into the API.
- [x] A request for an artifact that exists in one project is 404 when
      queried from a different project.
- [ ] An artifact whose frontmatter fails schema validation returns a
      structured error naming the offending field, not a 500.
- [ ] Cache hit ratio is measurable via a metric (`knowledge_cache_hit_total`).
- [ ] A missing cross-link (broken reference) is surfaced in the response
      rather than silently dropped.

## Metrics

- **Adoption:** every worker and the admin panel read knowledge
  exclusively through this API — 0 direct GitHub reads in the rebuilt
  codebase.
- **Latency:** p95 `GET .../knowledge/{type}/{id}` under 150ms on a warm
  cache.
- **Validation coverage:** 100% of artifact types have a Pydantic model
  matching their `_TEMPLATE.md`.

## Open questions

- Cache invalidation strategy — pull-on-read with TTL, GitHub webhook,
  or periodic sync? (Lifted from design `0004`'s open questions.)
- Do we pin reads to a specific git ref per request, or always `HEAD` of
  the default branch?
- Where does the GitHub App credential live — per-project or
  system-wide with per-project installation?

## Links

- Designs: [`0004`](../../designs/wip/0001-generalize-coder-from-vibetrade.md) (build plan step 2), [`0003`](../../designs/active/0003-knowledge-repo-model.md)
- ADRs: [`0001`](../../adrs/0001-knowledge-repo-layout.md), [`0002`](../../adrs/0002-yaml-registries.md), [`0008`](../../adrs/0008-ci-validation-of-knowledge-repo.md)
- Related specs: [`0001`](./0001-multi-tenant-project-crud.md), [`0003`](./0003-admin-panel-read-only.md)
