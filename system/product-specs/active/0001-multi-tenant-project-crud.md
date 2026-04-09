---
id: "0001"
title: Multi-tenant project CRUD
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0002", "0003"]
---

# Multi-tenant project CRUD

**Phase:** Now (foundation)
**Progress:** 6 / 6 acceptance criteria

## Problem

Today there is no Coder system running. The previous `coder-agent`
was hard-wired to a single project (VibeTrade) and cannot host a second
one. Every worker, API call, log line, and secret needs to be scoped to
a specific project, but no primitive exists yet to create, list, or
select a project. Without this, nothing else in the rebuild can be
multi-tenant — service accounts, knowledge repos, impersonation tokens,
and pipeline runs all need a `project_id` to attach to.

## Users / personas

- **Developer** building `coder-core` — needs a project table and CRUD
  endpoints to hang every other feature off of.
- **Software Architect** — needs to validate that project isolation is
  enforced at the API boundary, not bolted on later.
- **Local agent** (Claude Code, Cursor) impersonating a role — will
  eventually need to ask "which projects can I act on?" before doing
  anything.
- **Admin Panel** — read the project list on load; switch context.

## Goals

- `project_id` is a required dimension on every `coder-core` API call,
  log line, audit row, and emitted event.
- Projects can be created, listed, fetched, and archived via the Core
  API.
- Two projects existing simultaneously cannot see each other's data.
- The schema leaves room for per-project settings (knowledge repo URL,
  cloud account, GitHub org) without future migration churn.

## Non-goals

- Per-project RBAC beyond "member of project" (full ACL comes later).
- UI for project creation (the Admin Panel v0 is read-only — see spec
  `0003`).
- Project deletion with cascading cleanup — archive only for v0.
- Cross-project views or aggregations.

## Scope

- Postgres schema: `projects` table with `id`, `slug`, `name`,
  `knowledge_repo_url`, `github_org`, `gcp_project_id`, `status`,
  `created_at`, `archived_at`.
- FastAPI endpoints: `POST /projects`, `GET /projects`,
  `GET /projects/{id}`, `PATCH /projects/{id}`,
  `POST /projects/{id}:archive`.
- Middleware that extracts `project_id` from path or header and injects
  it into the request context.
- Structured logging: every log line emitted while handling a request
  carries `project_id`.
- Audit table: every write is recorded with actor, project_id, action.

## Acceptance criteria

- [x] `POST /projects` creates a project and returns its `id` and `slug`.
- [x] `GET /projects` lists only projects the caller has access to.
- [x] A request missing `project_id` on a project-scoped endpoint returns
      `400` (never falls through to a default).
- [x] Two projects created in the same test can be fetched independently;
      neither appears in the other's scoped queries.
- [x] Every log line emitted during a project-scoped request contains
      `project_id` as a structured field.
- [x] Archiving a project hides it from default listings but preserves
      audit history.

## Metrics

- **Correctness:** 100% of project-scoped endpoints reject requests
  without `project_id` in integration tests.
- **Isolation:** 0 cross-project reads in the isolation test suite.
- **Latency budget:** p95 on `GET /projects/{id}` under 50ms against a
  seed DB of 100 projects.

## Open questions

- Slug generation — caller-provided, auto-generated from name, or both?
- Soft-delete vs. archive — do we need both, or is archive enough for v0?
- Do we enforce project membership on `POST /projects` (who can create?)
  or leave that to the first human admin?

## Links

- Designs: [`0004`](../../designs/wip/0001-generalize-coder-from-vibetrade.md) (build plan step 2)
- ADRs: [`0005`](../../adrs/0005-multi-tenant-coder-core.md)
- Related specs: [`0002`](./0002-knowledge-repo-read-api.md), [`0003`](./0003-admin-panel-read-only.md)
