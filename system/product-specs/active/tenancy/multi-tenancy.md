---
id: multi-tenancy
title: Multi-tenancy
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-03
last_verified_at: 2026-05-03
summary: project_id everywhere invariant — no cross-tenant data access.
served_by_designs: []
related_specs: [admin-panel, audit-log, impersonation, knowledge-api, service-accounts, tenant-isolation]
parent: tenancy-and-access
---

# Multi-tenancy

## What it is

`project_id` is a first-class dimension on every API call, worker run,
log line, audit row, and emitted event in `coder-core`. Projects are the
isolation unit: workers, knowledge repos, secrets, service accounts,
pipeline runs, and impersonation tokens all attach to one. The system
assumes nothing is global — every read and write is project-scoped at
the API boundary, not bolted on later.

## Capabilities

- Create, list, fetch, and archive projects via the Core API.
- Enforces project scope on every project-aware endpoint: requests
  missing `project_id` are rejected with `400`, never silently defaulted.
- Cross-project reads return `404` — a resource in one project is
  invisible from another.
- Archiving hides a project from default listings while preserving
  audit history.
- Every log line emitted during a project-scoped request carries
  `project_id` as a structured field.
- Every write records an audit row with actor, project, and action.
- Per-project API keys with rotation.
- Schema accommodates per-project settings (knowledge repo URL, GitHub
  org, GCP project) without future migrations.

## Interfaces

- `POST /v1/projects` — create.
- `GET /v1/projects` — list (caller-scoped).
- `GET /v1/projects/{id}` — fetch.
- `PATCH /v1/projects/{id}` — update settings.
- `POST /v1/projects/{id}:archive` — archive.
- `projects` table in Postgres, `project_id` FK on every tenant-scoped
  table.
- Middleware that extracts `project_id` from path/header and injects it
  into request context + logger.

## Dependencies

- Postgres (source of truth for project records and audit trail).
- Structured logging pipeline (reads `project_id` from context).
- Auth middleware (maps API key / bearer token to an allowed project set).

## Evolution

- 0001 Multi-tenant project CRUD (shipped 2026-04) — established the
  `projects` table, CRUD endpoints, middleware injection of
  `project_id`, structured per-request logging, and the audit table.
  Added per-project API keys with rotate.

## Links

- Designs: [system-overview](../../../designs/active/system-overview.md),
  [tenancy-and-access](../../../designs/active/tenancy-and-access.md)
- Related components: [knowledge-api](../knowledge/knowledge-api.md),
  [admin-panel](../knowledge/admin-panel.md), [audit-log](./audit-log.md),
  [impersonation](./impersonation.md),
  [service-accounts](./service-accounts.md),
  [tenant-isolation](../delivery/tenant-isolation.md)
